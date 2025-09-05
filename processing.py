import os, re, io
import shutil
from typing import Optional
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from pathlib import Path
from functools import lru_cache

# ---------------- CONFIG ----------------
DEBUG = False  # set to True only when troubleshooting

# ---------------- Precompiled Regex ----------------
PART_PAT = re.compile(r'^\s*PART\s+[A-Z0-9 ]+', re.IGNORECASE)

# Specials that create a root-level parent directory
SPECIAL_PARENT_PAT = [
    re.compile(r'^\s*HONEYMOON\s*$', re.IGNORECASE),
    re.compile(r'^\s*AN INTERVIEW WITH THE WOMEN\'S MURDER CLUB\s*$', re.IGNORECASE),
]

# Specials that are sub-sections (go inside the current parent)
SPECIAL_PAT = [
    re.compile(r'^\s*PROLOGUE\s*$', re.IGNORECASE),
    re.compile(r'^\s*EPILOGUE\s*$', re.IGNORECASE),
]

CHAPTER_PATTERNS = [
    re.compile(r'^CHAPTER\s+(?:ONE\s+HUNDRED\s+(?:AND\s+)?(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY)?)$'),
    re.compile(r'^CHAPTER\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|SIXTY|SEVENTY|EIGHTY|NINETY)(?:\s*-\s*|\s+)?(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE)?$', re.IGNORECASE),
    re.compile(r'^CHAPTER\s+\d+$', re.IGNORECASE),
    re.compile(r'^CHAPTER\s+[IVX]+$', re.IGNORECASE)
]

# ---------------- Utilities ----------------
def debug_print(msg: str):
    if DEBUG:
        print(msg)

def save_page_as_pdf(page, out_file: Path):
    out_file.parent.mkdir(parents=True, exist_ok=True)
    new_doc = fitz.open()
    new_doc.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
    new_doc.save(str(out_file))
    new_doc.close()

@lru_cache(maxsize=None)
def ocr_page_cached(pdf_path: str, page_number: int, dpi: int = 200) -> str:
    with fitz.open(pdf_path) as doc:
        page = doc[page_number]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img, lang="eng")

def is_chapter_candidate(text: str) -> bool:
    t = text.strip().upper()
    # Heuristic: keep chapter headings short to avoid matching running headers
    if len(t) > 40:
        return False
    for pat in CHAPTER_PATTERNS:
        if pat.match(t):
            return True
    return False

def extract_heading_from_text(text: str) -> Optional[str]:
    """
    Extract heading string.
    Handles:
      - SPECIAL_PARENT (Honeymoon, Interview) including inline matches
      - PART
      - CHAPTER
      - SPECIAL (Prologue/Epilogue + optional subtitle like WHODUNWHAT)
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    # 1. Honeymoon special detection (inline or heading)
    for line in lines[:6]:
        if "HONEYMOON" in line.upper():
            if len(line.split()) <= 6 or line.strip().isupper():
                return "Honeymoon"

    # 2. Interview detection (can be multi-line)
    for end_line in range(1, min(6, len(lines) + 1)):
        candidate = " ".join(lines[:end_line])
        if "AN INTERVIEW WITH THE WOMEN" in candidate.upper():
            return "An Interview With The Women's Murder Club"

    # 3. PART
    for end_line in range(1, min(4, len(lines) + 1)):
        candidate = " ".join(lines[:end_line])
        if PART_PAT.match(candidate):
            return candidate.title().replace("  ", " ")

    # 4. CHAPTER
    for end_line in range(1, min(4, len(lines) + 1)):
        candidate = " ".join(lines[:end_line])
        if is_chapter_candidate(candidate):
            heading = candidate.title().replace("  ", " ")
            return f"{heading} Null Name"

    # 5. Specials (Prologue/Epilogue with subtitle)
    if lines[0].upper().startswith("PROLOGUE") or lines[0].upper().startswith("EPILOGUE"):
        subtitle = ""
        if len(lines) > 1 and lines[1].isupper():
            subtitle = " " + lines[1]
        return (lines[0] + subtitle).title().replace("  ", " ")

    # 5b. Scan first few lines for a Prologue/Epilogue heading not at line 1
    for idx in range(1, min(6, len(lines))):
        if lines[idx].upper().startswith("PROLOGUE") or lines[idx].upper().startswith("EPILOGUE"):
            subtitle = ""
            if idx + 1 < len(lines) and lines[idx + 1].isupper():
                subtitle = " " + lines[idx + 1]
            return (lines[idx] + subtitle).title().replace("  ", " ")

    # 6. Fallback wide-scan for Honeymoon/Interview when no heading found
    upper_text = text.upper()
    if " HONEYMOON" in upper_text or upper_text.startswith("HONEYMOON"):
        return "Honeymoon"
    if "AN INTERVIEW WITH THE WOMEN" in upper_text:
        return "An Interview With The Women's Murder Club"

    return None

def is_blank_page(text: str) -> bool:
    s = text.strip()
    if not s:
        return True
    # If the page contains only a small number or minimal characters, treat as blank/number-only
    if s.isdigit() and len(s) <= 3:
        return True
    if len(s) <= 5:
        return True
    return False

def extract_page_number_from_text(text: str, default_page_index: int) -> int:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return default_page_index + 1
    last_line = lines[-1]
    if last_line.isdigit():
        return int(last_line)
    return default_page_index + 1

def clean_directory_name(name: str) -> str:
    if not name:
        return ""
    name = name.replace(" ", "_")
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name

# ---------------- Main Processing ----------------
def process_pdf(pdf_path: str, output_root: str, reference_zip_root_name: str, aggressive_ocr: bool = False):
    root_dup = reference_zip_root_name
    book_base = reference_zip_root_name
    results = []
    debug_log = []
    created_dirs = set()
    # Track display page numbering across Parts:
    # First Part starts at 1; successive Parts continue numbering (+1 from last)
    part_sequence_started = False
    part_page_counter = 0

    # Create Whole Book folder and copy original PDF into it
    whole_book_root = Path(output_root) / root_dup / root_dup / f"{book_base}_Whole_Book"
    whole_book_root.mkdir(parents=True, exist_ok=True)
    try:
        src_pdf = Path(pdf_path)
        if src_pdf.exists():
            dest_pdf = whole_book_root / src_pdf.name
            if not dest_pdf.exists():
                shutil.copy2(str(src_pdf), str(dest_pdf))
            debug_log.append(f"Whole book copied to: {dest_pdf}")
        else:
            debug_log.append(f"Source PDF not found for whole book copy: {pdf_path}")
    except Exception as e:
        debug_log.append(f"Failed to copy whole book PDF: {e}")

    with fitz.open(pdf_path) as doc:
        n = doc.page_count
        debug_log.append(f"Processing PDF with {n} pages")

        current_parent = None
        current_part = None
        current_chapter = None
        seen_first_content = False
        # Lock a few pages after setting a parent to keep early pages inside parent
        parent_lock_remaining = 0

        def detect_upcoming_child(start_index: int) -> Optional[str]:
            """Look ahead a couple of pages to see if a child section starts soon."""
            lookahead_limit = min(n, start_index + 3)
            for j in range(start_index + 1, lookahead_limit):
                nxt = doc[j]
                nxt_text = nxt.get_text("text")
                if aggressive_ocr and not nxt_text.strip():
                    nxt_text = ocr_page_cached(pdf_path, j)
                nxt_heading = extract_heading_from_text(nxt_text) or ""
                u = nxt_heading.upper()
                if u.startswith("PART") or u.startswith("CHAPTER") or u.startswith("PROLOGUE") or u.startswith("EPILOGUE"):
                    return nxt_heading
            return None

        def get_and_advance_part_page_number() -> int:
            nonlocal part_sequence_started, part_page_counter
            if not part_sequence_started:
                part_sequence_started = True
                part_page_counter = 1
                return 1
            else:
                part_page_counter += 1
                return part_page_counter

        for i, page in enumerate(doc):
            text = page.get_text("text")
            page_number = extract_page_number_from_text(text, page.number)

            if aggressive_ocr and not text.strip():
                text = ocr_page_cached(pdf_path, i)

            heading = extract_heading_from_text(text)
            # During parent lock, ignore chapter headings to avoid running-header false positives
            if heading and heading.upper().startswith("CHAPTER") and parent_lock_remaining > 0:
                heading = None
            debug_info = f"Page {i} (printed: {page_number})"

            # COVER (first 4 pages)
            if i < 4:
                cover_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_Cover"
                cover_dir.mkdir(parents=True, exist_ok=True)
                filename = [
                    f"{book_base}_Front_Outer.pdf",
                    f"{book_base}_Front_Inner.pdf",
                    f"{book_base}_Back_Inner.pdf",
                    f"{book_base}_Back_Outer.pdf"
                ][i]
                out_file = cover_dir / filename
                save_page_as_pdf(page, out_file)
                results.append({"page": i, "out": str(out_file)})
                debug_log.append(f"{debug_info}: COVER -> {filename}")
                continue

            section_dir, filename, section_type = None, None, None

            # --- Handle Headings ---
            if heading:
                h_upper = heading.upper()

                # SPECIAL PARENT (Honeymoon, Interview)
                if "HONEYMOON" in h_upper or "AN INTERVIEW" in h_upper:
                    current_parent = clean_directory_name(heading.title())
                    current_part = None
                    current_chapter = None
                    seen_first_content = True
                    parent_lock_remaining = 2
                    section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}"
                    filename = f"{book_base}_{current_parent}_Page {page_number}.pdf"
                    section_type = f"Parent: {current_parent}"

                # PART
                elif h_upper.startswith("PART"):
                    current_part = clean_directory_name(heading.title())
                    current_chapter = None
                    seen_first_content = True
                    if current_parent:
                        section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}" / f"{book_base}_{current_parent}_{current_part}"
                        page_num_for_filename = get_and_advance_part_page_number()
                        filename = f"{book_base}_{current_parent}_{current_part}_Page {page_num_for_filename}.pdf"
                        section_type = f"Part under parent: {current_parent}/{current_part}"
                    else:
                        section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_part}"
                        page_num_for_filename = get_and_advance_part_page_number()
                        filename = f"{book_base}_{current_part}_Page {page_num_for_filename}.pdf"
                        section_type = f"Part (root): {current_part}"

                # CHAPTER
                elif h_upper.startswith("CHAPTER") or is_chapter_candidate(heading):
                    current_chapter = clean_directory_name(heading.title())
                    seen_first_content = True
                    if current_parent and current_part:
                        section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}" / f"{book_base}_{current_parent}_{current_part}" / f"{book_base}_{current_parent}_{current_part}_{current_chapter}"
                        page_num_for_filename = get_and_advance_part_page_number()
                        filename = f"{book_base}_{current_parent}_{current_part}_{current_chapter}_Page {page_num_for_filename}.pdf"
                        section_type = f"Chapter under parent+part: {current_parent}/{current_part}/{current_chapter}"
                    elif current_parent:
                        section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}" / f"{book_base}_{current_parent}_{current_chapter}"
                        filename = f"{book_base}_{current_parent}_{current_chapter}_Page {page_number}.pdf"
                        section_type = f"Chapter under parent: {current_parent}/{current_chapter}"
                    elif current_part:
                        section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_part}" / f"{book_base}_{current_part}_{current_chapter}"
                        page_num_for_filename = get_and_advance_part_page_number()
                        filename = f"{book_base}_{current_part}_{current_chapter}_Page {page_num_for_filename}.pdf"
                        section_type = f"Chapter under part: {current_part}/{current_chapter}"
                    else:
                        section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_chapter}"
                        filename = f"{book_base}_{current_chapter}_Page {page_number}.pdf"
                        section_type = f"Chapter: {current_chapter}"

                # PROLOGUE / EPILOGUE
                elif h_upper.startswith("PROLOGUE") or h_upper.startswith("EPILOGUE"):
                    current_chapter = clean_directory_name(heading.title())
                    seen_first_content = True
                    if current_parent:
                        section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}" / f"{book_base}_{current_parent}_{current_chapter}"
                        filename = f"{book_base}_{current_parent}_{current_chapter}_Page {page_number}.pdf"
                        section_type = f"Special under parent: {current_parent}/{current_chapter}"
                    elif current_part:
                        section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_part}" / f"{book_base}_{current_part}_{current_chapter}"
                        page_num_for_filename = get_and_advance_part_page_number()
                        filename = f"{book_base}_{current_part}_{current_chapter}_Page {page_num_for_filename}.pdf"
                        section_type = f"Special under part: {current_part}/{current_chapter}"
                    else:
                        section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_chapter}"
                        filename = f"{book_base}_{current_chapter}_Page {page_number}.pdf"
                        section_type = f"Special: {current_chapter}"

            # --- Fallback for non-heading pages ---
            if section_dir is None:
                if not seen_first_content:
                    section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_Index"
                    filename = f"{book_base}_Index_Page {i-3}.pdf"
                    section_type = "Index"
                elif current_parent and not current_part and not current_chapter:
                    # We're in a parent-only state; try to foresee the next child section
                    upcoming = detect_upcoming_child(i)
                    if upcoming:
                        up_upper = upcoming.upper()
                        if up_upper.startswith("PROLOGUE") or up_upper.startswith("EPILOGUE"):
                            child = clean_directory_name(upcoming.title())
                            section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}" / f"{book_base}_{current_parent}_{child}"
                            filename = f"{book_base}_{current_parent}_{child}_Page {page_number}.pdf"
                            section_type = f"Preceding page routed to upcoming special under parent: {current_parent}/{child}"
                        elif up_upper.startswith("PART"):
                            child = clean_directory_name(upcoming.title())
                            section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}" / f"{book_base}_{current_parent}_{child}"
                            filename = f"{book_base}_{current_parent}_{child}_Page {page_number}.pdf"
                            section_type = f"Preceding page routed to upcoming part under parent: {current_parent}/{child}"
                        elif up_upper.startswith("CHAPTER"):
                            # Rare: chapter directly under parent; place under parent+chapter
                            child = clean_directory_name(upcoming.title())
                            section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}" / f"{book_base}_{current_parent}_{child}"
                            filename = f"{book_base}_{current_parent}_{child}_Page {page_number}.pdf"
                            section_type = f"Preceding page routed to upcoming chapter under parent: {current_parent}/{child}"
                    else:
                        section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}"
                        filename = f"{book_base}_{current_parent}_Page {page_number}.pdf"
                        section_type = "Page inside parent"
                elif current_parent and current_part and current_chapter:
                    section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}" / f"{book_base}_{current_parent}_{current_part}" / f"{book_base}_{current_parent}_{current_part}_{current_chapter}"
                    page_num_for_filename = get_and_advance_part_page_number()
                    filename = f"{book_base}_{current_parent}_{current_part}_{current_chapter}_Page {page_num_for_filename}.pdf"
                    section_type = "Page inside parent+part+chapter"
                elif current_parent and current_part:
                    section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}" / f"{book_base}_{current_parent}_{current_part}"
                    page_num_for_filename = get_and_advance_part_page_number()
                    filename = f"{book_base}_{current_parent}_{current_part}_Page {page_num_for_filename}.pdf"
                    section_type = "Page inside parent+part"
                elif current_parent:
                    section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_parent}"
                    filename = f"{book_base}_{current_parent}_Page {page_number}.pdf"
                    section_type = "Page inside parent"
                elif current_part and current_chapter:
                    section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_part}" / f"{book_base}_{current_part}_{current_chapter}"
                    page_num_for_filename = get_and_advance_part_page_number()
                    filename = f"{book_base}_{current_part}_{current_chapter}_Page {page_num_for_filename}.pdf"
                    section_type = "Page inside part+chapter"
                elif current_part:
                    section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_part}"
                    page_num_for_filename = get_and_advance_part_page_number()
                    filename = f"{book_base}_{current_part}_Page {page_num_for_filename}.pdf"
                    section_type = "Page inside part"
                else:
                    section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_Back_Index"
                    filename = f"{book_base}_Back_Index_Page {page_number}.pdf"
                    section_type = "Back Index"

            # Save file
            section_dir.mkdir(parents=True, exist_ok=True)
            out_file = section_dir / filename
            save_page_as_pdf(page, out_file)

            debug_log.append(f"{debug_info}: {('Heading '+heading) if heading else 'No heading'} -> {section_type}")
            results.append({
                "page": i,
                "out": str(out_file),
                "heading": heading,
                "section": str(section_dir),
                "current_parent": current_parent,
                "current_part": current_part,
                "current_chapter": current_chapter
            })

            # Decrement parent lock after processing this page
            if parent_lock_remaining > 0:
                parent_lock_remaining -= 1

    debug_file = Path(output_root) / f"{book_base}_processing_debug.log"
    with open(debug_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(debug_log))

    print(f"Debug log saved to: {debug_file}")
    print(f"Processed {len(results)} pages")
    return results

# Compatibility wrapper for debug script
def ocr_page(page, dpi: int = 200) -> str:
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img, lang="eng")
