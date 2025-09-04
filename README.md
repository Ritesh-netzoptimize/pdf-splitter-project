# Book Page Splitter — FastAPI

Split a scanned book PDF into **per-page PDFs** and sort them into a directory
structure and file naming convention **matching your reference zip**.

## Features
- Preserves original page dimensions (smaller than A4 is fine).
- Extracts **book page numbers** from the footer (text or OCR).
- Heuristically detects sections: **Cover, Front Index, Parts, Chapters, Prologue/Epilogue**, and
  special sections (e.g., *Honeymoon*, *An Interview With The Women's Murder Club*).
- Creates directories & filenames modeled after your sample:
  `WF_2141_3rd Degree_<Section>[_<Subsection>]..._Page <book_page>.pdf`
  (uses `Null` placeholders when something is missing).
- Multi-core processing for speed.

## Quickstart (Windows)
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

set TESSDATA_PREFIX=C:\Program Files\Tesseract-OCR\tessdata
# If tesseract is not on PATH, set (adjust path as installed)
set PATH=%PATH%;C:\Program Files\Tesseract-OCR

uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Open http://127.0.0.1:8000/docs to use the API.

## API
- `POST /process` — JSON body:
  ```json
  {
    "pdf_path": "C:/path/to/book.pdf",
    "output_root": "C:/path/to/output",
    "reference_zip_root_name": "WF_2141_3rd Degree",
    "aggressive_ocr": false
  }
  ```
  The app will create: `<output_root>/<Root>/<Root>/<Section>/.../Page N.pdf`
  mirroring the `WF_2141_3rd Degree/WF_2141_3rd Degree/...` pattern.

## Notes
- OCR is only used when PDF text is missing; set `aggressive_ocr=true` to force OCR
  (slower but robust).
- If a cue (e.g., chapter title) is missing, the code inserts `Null` placeholders
  to keep names consistent.
