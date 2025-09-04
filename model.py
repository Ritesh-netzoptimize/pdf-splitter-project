from pydantic import BaseModel, Field
from typing import Optional
class ProcessRequest(BaseModel):
    pdf_path: str = Field(..., description="Path to the source book PDF")
    output_root: str = Field(..., description="Directory where output tree will be created")
    reference_zip_root_name: str = Field("WF_2141_3rd Degree", description="Duplicated root dir name to mirror")
    aggressive_ocr: bool = Field(False, description="Force OCR on all pages (slower)")