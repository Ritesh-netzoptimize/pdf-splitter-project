import os, re, math, concurrent.futures
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import numpy as np
from pathlib import Path


# ---------- Heuristics & utilities ----------
import io

def save_page_as_pdf(page, out_file: Path):
    """
    Save a single PyMuPDF page as its own PDF file.
    """
    out_file.parent.mkdir(parents=True, exist_ok=True)

    new_doc = fitz.open()           # create new empty PDF
    new_doc.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
    new_doc.save(str(out_file))
    new_doc.close()


def ocr_page(page):
    """
    Run OCR on a PyMuPDF page and return extracted text.
    """
    pix = page.get_pixmap(dpi=300)  # render page at 300 DPI
    img_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_bytes))
    text = pytesseract.image_to_string(img, lang="eng")
    return text

def extract_heading(page, aggressive_ocr=False):
    text = page.get_text("text")
    if aggressive_ocr and not text.strip():
        text = ocr_page(page)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    first_line = lines[0]
    if re.match(r'^\s*PART\s+\w+', first_line, re.IGNORECASE):
        return first_line
    if re.match(r'^\s*CHAPTER\s+\w+', first_line, re.IGNORECASE):
        return first_line
    return None



def extract_page_number(page):
    """
    Try to extract the page number printed at the bottom of the page.
    Falls back to PDF index if no number found.
    """
    text = page.get_text("text")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return page.number + 1  # fallback to logical PDF index

    # Take last line as candidate for page number
    last_line = lines[-1]
    if last_line.isdigit():
        return int(last_line)

    return page.number + 1


UPCASE = re.compile(r"^[A-Z0-9 \-:'\.,]+$")

PART_RX = re.compile(r"\bPART\s+(ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|[IVXLC]+)\b", re.I)
CHAPTER_RX = re.compile(r"\bCHAPTER\s+([A-Z0-9]+)\b", re.I)
PRO_EPILOGUE_RX = re.compile(r"\b(PROLOGUE|EPILOGUE)\b", re.I)
CONTENTS_RX = re.compile(r"\bCONTENTS\b", re.I)

SPECIAL_SECTIONS = [
    "HONEYMOON",
    "AN INTERVIEW WITH THE WOMEN'S MURDER CLUB",
]

DIGITS_RX = re.compile(r"(?:^|\D)(\d{1,4})(?:\D|$)")

@dataclass
class PageContext:
    part_label: Optional[str] = None
    part_title: Optional[str] = None
    chapter_label: Optional[str] = None
    chapter_title: Optional[str] = None

@dataclass
class PageDecision:
    section_dir: str
    file_name: str
    book_page_number: int
    debug: Dict[str, str] = field(default_factory=dict)

def ocr_image(img: Image.Image, psm: int = 6) -> str:
    # PSM 6 = Assume a single uniform block of text
    try:
        txt = pytesseract.image_to_string(img, config=f"--psm {psm}")
    except Exception:
        return ""
    return txt or ""

def page_to_image(page, zoom: float = 2.0) -> Image.Image:
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return img

def extract_text_blocks_top(page, fraction: float = 0.3) -> str:
    # Prefer PDF text
    try:
        blocks = page.get_text("blocks")  # (x0, y0, x1, y1, "text", block_no, block_type)
    except Exception:
        blocks = []
    if blocks:
        h = page.rect.height
        top_blocks = [b for b in blocks if b[1] <= h * fraction]
        top_blocks.sort(key=lambda b: (b[1], b[0]))
        return "\n".join((b[4] or "").strip() for b in top_blocks if (b[4] or "").strip())
    # Fallback OCR on top region
    img = page_to_image(page, 2.0)
    w, h = img.size
    crop = img.crop((0, 0, w, int(h * fraction)))
    return ocr_image(crop, psm=4)

def extract_page_number_bottom(page) -> Optional[int]:
    # Try PDF text near bottom
    h = page.rect.height
    try:
        blocks = page.get_text("blocks")
    except Exception:
        blocks = []
    lines = []
    if blocks:
        bottom_blocks = [b for b in blocks if b[1] >= h * 0.80]
        bottom_blocks.sort(key=lambda b: (b[1], b[0]))
        for b in bottom_blocks:
            t = (b[4] or "").strip()
            if t:
                lines.append(t)
    text_bottom = " ".join(lines)
    for m in DIGITS_RX.finditer(text_bottom):
        try:
            val = int(m.group(1))
            if 1 <= val <= 2000:
                return val
        except Exception:
            pass
    # OCR bottom strip
    img = page_to_image(page, 2.0)
    w, h = img.size
    crop = img.crop((0, int(h*0.82), w, h))
    text = ocr_image(crop, psm=7)
    for m in DIGITS_RX.finditer(text):
        try:
            val = int(m.group(1))
            if 1 <= val <= 2000:
                return val
        except Exception:
            pass
    return None

def classify_section(head_text: str, ctx: PageContext) -> Tuple[str, PageContext, Dict[str,str]]:
    debug = {}
    t = " ".join(head_text.split())
    u = t.upper()
    debug['head_text'] = t

    # Special named sections
    for s in SPECIAL_SECTIONS:
        if s in u:
            ctx.part_label = None
            ctx.part_title = None
            ctx.chapter_label = None
            ctx.chapter_title = None
            return (s.title(), ctx, {**debug, "match": f"SPECIAL:{s}"})

    # Cover / Front Index heuristics (very early pages often have no part/chapter)
    if CONTENTS_RX.search(t):
        return ("Front Index", ctx, {**debug, "match": "CONTENTS"})

    pe = PRO_EPILOGUE_RX.search(t)
    if pe:
        lab = pe.group(1).title()
        ctx.chapter_label = lab
        ctx.chapter_title = None
        return (lab, ctx, {**debug, "match": "PRO_EPILOGUE"})

    pm = PART_RX.search(t)
    if pm:
        roman = pm.group(1).title()
        ctx.part_label = f"Part {roman}"
        # Try to get a title line below "PART ..."
        # Heuristic: pick next longest uppercase word sequence after match
        after = t[pm.end():].strip(" -:")
        title = None
        # Choose a reasonable short title token
        m2 = re.search(r"([A-Z][A-Za-z0-9' ]{3,60})", after)
        if m2:
            title = m2.group(1).strip()
        ctx.part_title = title
        ctx.chapter_label = None
        ctx.chapter_title = None
        return (ctx.part_label, ctx, {**debug, "match": "PART", "part_title": str(title)})

    cm = CHAPTER_RX.search(t)
    if cm:
        lab = cm.group(0).title()
        ctx.chapter_label = lab  # full "Chapter One"
        # try title after chapter line
        after = t[cm.end():].strip(" -:")
        title = None
        m3 = re.search(r"([A-Z][A-Za-z0-9' ]{3,60})", after)
        if m3:
            title = m3.group(1).strip()
        ctx.chapter_title = title
        return ("Chapter", ctx, {**debug, "match": "CHAPTER", "chapter_title": str(title)})

    # Otherwise, keep current context; this is a normal page
    label = (
        ctx.part_label or
        "Front Index"  # before first part
    )
    return (label, ctx, {**debug, "match": "FLOW"})

def safe_name(s: Optional[str]) -> str:
    if not s: 
        return "Null Name"
    s = re.sub(r"[\s]+", " ", s).strip()
    s = s.replace("/", "-").replace("\\", "-").replace(":", " -")
    return s

def build_paths(root_name: str, book_base: str, section: str, ctx: PageContext, page_no: int) -> Tuple[str, str]:
    # Directory tree: <root>/<root>/<book_base>_<Section or Part>/<...>
    # Sample: WF_2141_3rd Degree/WF_2141_3rd Degree/WF_2141_3rd Degree_Part One/...
    section_dir = f"{book_base}_{section.replace('/', '-')}"

    # File name parts
    parts = [book_base]
    # If Part context applies, include "Part X" and optional title
    if ctx.part_label:
        parts.append(ctx.part_label)
        parts.append(safe_name(ctx.part_title))
    # If chapter context applies
    if ctx.chapter_label:
        parts.append(ctx.chapter_label)
        parts.append(safe_name(ctx.chapter_title))
    # Always end with page
    parts.append(f"Page {page_no}")
    file_name = "_".join(p for p in parts if p).replace("__", "_") + ".pdf"
    return section_dir, file_name

def process_single_page(args):
    (pdf_path, out_root, dup_root, book_base, i, ctx_snapshot, force_ocr) = args
    with fitz.open(pdf_path) as doc:
        page = doc.load_page(i)
        head_text = extract_text_blocks_top(page, 0.33)
        if force_ocr or not head_text.strip():
            # OCR the top strip if needed (already does)
            pass
        section, ctx_out, dbg = classify_section(head_text, ctx_snapshot)

        # Get book page number
        book_no = extract_page_number_bottom(page)
        if book_no is None:
            # fallback to i+1 if unknown
            book_no = i + 1
            dbg['page_no_fallback'] = True

        # Directory + filename
        section_dir, file_name = build_paths(dup_root, book_base, section, ctx_out, book_no)

        # Build final output path
        # Pattern: <out_root>/<dup_root>/<dup_root>/<section_dir>/<file_name>
        final_dir = os.path.join(out_root, dup_root, dup_root, section_dir)
        os.makedirs(final_dir, exist_ok=True)
        out_pdf = os.path.join(final_dir, file_name)

        # Write 1-page PDF preserving original size
        dst = fitz.open()
        src = fitz.open(pdf_path)
        dst.insert_pdf(src, from_page=i, to_page=i)
        dst.save(out_pdf, deflate=True, clean=True)
        dst.close()
        src.close()
        return {"page": i, "out": out_pdf, "ctx": ctx_out, "section": section, "book_page": book_no, "debug": dbg}

def process_pdf(pdf_path: str, output_root: str, reference_zip_root_name: str, aggressive_ocr: bool = False):
    root_dup = reference_zip_root_name
    book_base = reference_zip_root_name

    with fitz.open(pdf_path) as doc:
        n = doc.page_count

        current_part = None
        current_chapter = None
        seen_first_content = False
        results = []

        for i in range(n):
            page = doc[i]
            heading = extract_heading(page, aggressive_ocr)
            page_number = extract_page_number(page)

            # Detect Part
            if heading and heading.upper().startswith("PART"):
                current_part = heading.title().replace(" ", "_")
                current_chapter = None
                seen_first_content = True

            # Detect Chapter
            elif heading and heading.upper().startswith("CHAPTER"):
                if current_part:  # only allow chapters inside a part
                    current_chapter = heading.title().replace(" ", "_")
                else:
                    current_chapter = heading.title().replace(" ", "_")  # fallback
                seen_first_content = True

            # Section assignment
            if not seen_first_content:
                # Before any part/chapter
                section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_Front_Index"
            elif current_part and current_chapter:
                # Inside chapter under a part
                section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_part}" / f"{book_base}_{current_part}_{current_chapter}"
            elif current_part:
                # Just part, no chapter yet
                section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_part}"
            else:
                # After last content
                section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_Back_Index"

            section_dir.mkdir(parents=True, exist_ok=True)

            # Build output filename
            if current_part and current_chapter:
                filename = f"{book_base}_{current_part}_{current_chapter}_Page {page_number}.pdf"
            elif current_part:
                filename = f"{book_base}_{current_part}_Page {page_number}.pdf"
            elif not seen_first_content:
                filename = f"{book_base}_Front_Index_Page {page_number}.pdf"
            else:
                filename = f"{book_base}_Back_Index_Page {page_number}.pdf"

            out_file = section_dir / filename
            save_page_as_pdf(page, out_file)

            results.append({"page": i, "out": str(out_file)})

    return results
