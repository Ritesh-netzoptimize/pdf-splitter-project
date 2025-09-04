from fastapi import FastAPI, HTTPException, UploadFile, File, Form
import os, shutil, tempfile
from pathlib import Path
from processing import process_pdf

app = FastAPI(title="Book Page Splitter")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/process")
def process(
    file: UploadFile = File(...),
    output_root: str = Form(...),
    reference_zip_root_name: str = Form(...),
    aggressive_ocr: bool = Form(False),
):
    try:
        # Save uploaded file temporarily
        temp_dir = tempfile.mkdtemp()
        pdf_path = Path(temp_dir) / file.filename
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Ensure output dir exists
        os.makedirs(output_root, exist_ok=True)

        # Call your existing processing logic
        results = process_pdf(
            pdf_path=str(pdf_path),
            output_root=output_root,
            reference_zip_root_name=reference_zip_root_name,
            aggressive_ocr=aggressive_ocr,
        )

        return {
            "pages": len(results),
            "output_root": output_root,
            "sample_outputs": [r["out"] for r in results[:10]],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))