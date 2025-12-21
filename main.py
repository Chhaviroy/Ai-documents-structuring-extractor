from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import pandas as pd
import os
from PyPDF2 import PdfReader
import uvicorn
import google.generativeai as genai
from dotenv import load_dotenv
import json
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import re

# Load environment variables
load_dotenv('.env')
api_key = os.getenv('API_KEY')

# Configure generative AI
if not api_key:
    raise ValueError("API_KEY not found in .env file")
genai.configure(api_key=api_key)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

@app.post("/convert-to-excel/")
async def convert_to_excel(file: UploadFile = File(...)):
    # Check if the uploaded file is a PDF
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only .pdf files are allowed.")

    # Read PDF
    content = await file.read()
    with open("temp.pdf", "wb") as temp_file:
        temp_file.write(content)
    reader = PdfReader("temp.pdf")
    text_data = "\n".join([page.extract_text() or "" for page in reader.pages])
    os.remove("temp.pdf")

    # Prepare prompt for AI
    prompt = f"""
    Extract ALL information from the following text.

    Rules:
    - Do NOT summarize.
    - Capture 100% information.
    - Detect all key:value relationships.
    - For each key, add a comment containing related context from the text.
    - Output ONLY valid JSON list of objects, format:
      [
        {{"key": "...", "value": "...", "comments": "..."}} 
      ]

    Text:
    {text_data}
    """

    # Call the LLM
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    response = model.generate_content(prompt)

    # Safely extract JSON using regex
    match = re.search(r"\[.*\]", response.text, re.DOTALL)
    if not match:
        raise HTTPException(status_code=500, detail="AI did not return valid JSON.")

    clean_json = match.group(0)

    try:
        data = json.loads(clean_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse JSON from AI response.")

    # Convert to DataFrame
    df = pd.DataFrame(data)
    output_file = "output.xlsx"
    df.to_excel(output_file, index=False)

    return FileResponse(
        output_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_file
    )

# Cleanup Excel on shutdown
@app.on_event("shutdown")
def cleanup():
    if os.path.exists("output.xlsx"):
        os.remove("output.xlsx")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

print("API KEY LOADED:", api_key[:6])
