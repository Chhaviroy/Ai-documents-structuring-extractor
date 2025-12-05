from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import pandas as pd
import os
from PyPDF2 import PdfReader
import uvicorn
import google.generativeai as genai
from dotenv import load_dotenv
import json
import re
import tempfile

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
    # Validate PDF
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only .pdf files are allowed.")

    # Save uploaded PDF to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
        temp_pdf.write(content)
        temp_pdf_path = temp_pdf.name

    try:
        # Read PDF content
        reader = PdfReader(temp_pdf_path)
        text_data = "\n".join([page.extract_text() or "" for page in reader.pages])
        if not text_data.strip():
            raise HTTPException(status_code=400, detail="PDF contains no extractable text.")
    finally:
        os.remove(temp_pdf_path)  # Clean up temp PDF

    # Define prompt for LLM
    prompt = f"""
    Extract ALL information from the following text.

    Rules:
    - Do NOT summarize.
    - Capture 100% information.
    - Detect all key:value relationships.
    - For each key, add a comment containing related context from the text.
    - Output ONLY valid JSON list of objects, format:
      [
        {{"key": "...", "value": "...", "comments": "..."}} ,
        ...
      ]

    Text:
    {text_data}
    """

    # Generate content using the LLM
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")
    response = model.generate_content(prompt)

    # Safely extract JSON from LLM output
    try:
        match = re.search(r"\[\s*\{.*\}\s*\]", response.text, re.DOTALL)
        if not match:
            raise HTTPException(status_code=500, detail="LLM did not return valid JSON.")
        clean_json = match.group()
        data = json.loads(clean_json)
        if not data:
            raise HTTPException(status_code=500, detail="No data extracted from PDF.")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse JSON from LLM output: {str(e)}")

    # Convert to Excel
    df = pd.DataFrame(data)
    output_file = "output.xlsx"
    df.to_excel(output_file, index=False)

    return FileResponse(
        output_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=output_file
    )

# Cleanup generated Excel file after shutdown
@app.on_event("shutdown")
def cleanup():
    if os.path.exists("output.xlsx"):
        os.remove("output.xlsx")
        
if __name__ == "__main__":
    uvicorn.run(app)

