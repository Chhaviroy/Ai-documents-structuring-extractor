from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import pandas as pd
import os
from PyPDF2 import PdfReader
import uvicorn
import google.generativeai as genai
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv('.env')
api_key = os.getenv('API_KEY')

# Configure generative AI
if not api_key:
    raise ValueError("API_KEY not found in .env file")
genai.configure(api_key=api_key)

app = FastAPI()

@app.post("/convert-to-excel/")
async def convert_to_excel(file: UploadFile = File(...)):
    # Check if the uploaded file is a PDF
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only .pdf files are allowed.")

    # Process the PDF file
    content = await file.read()
    with open("temp.pdf", "wb") as temp_file:
        temp_file.write(content)
    reader = PdfReader("temp.pdf")
    text_data = "\n".join([page.extract_text() for page in reader.pages])
    os.remove("temp.pdf")

    # Define the prompt for the LLM
    prompt = f"""
    Extract ALL information from the following text.

    Rules:
    - Do NOT summarize.
    - Capture 100% information.
    - Detect all key:value relationships.
    - For each key, add a comment containing related context from the text.
    - Output ONLY valid JSON list of objects, format:
      [
        {{"key": "...", "value": "...", "comments": "..."}},
        ...
      ]

    Text:
    {text_data}
    """

    # Generate content using the LLM
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    response = model.generate_content(prompt)

    # Parse the response
    clean_json = response.text.strip().replace("json", "").replace("", "")
    data = json.loads(clean_json)

    # Convert the extracted data to a DataFrame
    df = pd.DataFrame(data)
    output_file = "output.xlsx"
    df.to_excel(output_file, index=False)

    # Return the Excel file as a response
    return FileResponse(output_file, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=output_file)

# Cleanup: Remove the generated Excel file after the response
@app.on_event("shutdown")
def cleanup():
    if os.path.exists("output.xlsx"):
        os.remove("output.xlsx")

if __name__ == "__main__":
    uvicorn.run(app)
