import os, re, io
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from pathlib import Path

# More flexible patterns
PART_PAT = re.compile(r'^\s*PART\s+[A-Z0-9 ]+', re.IGNORECASE)
SPECIAL_PAT = [
    re.compile(r'^\s*PROLOGUE\s*$', re.IGNORECASE),
    re.compile(r'^\s*EPILOGUE\s*$', re.IGNORECASE),
    re.compile(r'^\s*HONEYMOON\s*$', re.IGNORECASE),
    re.compile(r'^\s*AN INTERVIEW WITH THE WOMEN\'S MURDER CLUB\s*$', re.IGNORECASE),
]
# ---------- Utilities ----------

def save_page_as_pdf(page, out_file: Path):
    """Save a single PyMuPDF page as its own PDF file."""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    new_doc = fitz.open()
    new_doc.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
    new_doc.save(str(out_file))
    new_doc.close()

def ocr_page(page):
    """Run OCR on a PyMuPDF page and return extracted text."""
    pix = page.get_pixmap(dpi=300)
    img_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_bytes))
    text = pytesseract.image_to_string(img, lang="eng")
    return text


def is_chapter_heading(text_lines):
    """
    More robust chapter detection that handles various formats and multi-line titles.
    Returns (is_chapter, chapter_title) tuple.
    """
    if not text_lines:
        return False, None
    
    print(f"DEBUG: is_chapter_heading received {len(text_lines)} lines:")
    for i, line in enumerate(text_lines[:10]):  # Show first 10 lines
        print(f"DEBUG:   Line {i}: '{line}' (length: {len(line)})")
    
    # Try different combinations of lines to build chapter title
    for num_lines in range(1, min(8, len(text_lines) + 1)):
        candidate = " ".join(text_lines[:num_lines]).strip()
        
        # Remove extra whitespace
        candidate = re.sub(r'\s+', ' ', candidate)
        
        print(f"DEBUG: Trying {num_lines} lines: '{candidate}'")
        
        # Check if it starts with CHAPTER (case insensitive)
        if re.match(r'^\s*CHAPTER\s+', candidate, re.IGNORECASE):
            # Additional validation - make sure it's not just "CHAPTER" alone
            chapter_part = re.sub(r'^\s*CHAPTER\s+', '', candidate, flags=re.IGNORECASE).strip()
            if chapter_part:  # Must have something after "CHAPTER"
                print(f"DEBUG: Found valid chapter: '{candidate.title()}'")
                return True, candidate.title()
    
    print("DEBUG: No valid chapter found")
    return False, None

def extract_heading(page, aggressive_ocr=False):
    """Extract heading text (Part/Chapter, multi-line safe) with debug output."""
    print(f"\nDEBUG: extract_heading called for page")
    
    # Try regular text extraction first
    text = page.get_text("text")
    print(f"DEBUG: Regular text extraction result: {len(text)} characters")
    
    if aggressive_ocr and not text.strip():
        print("DEBUG: Using aggressive OCR...")
        text = ocr_page(page)
        print(f"DEBUG: OCR result: {len(text)} characters")
    
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    print(f"DEBUG: Extracted {len(lines)} non-empty lines")
    
    if not lines:
        print("DEBUG: No lines found, returning None")
        return None

    # Show first few lines of extracted text
    print("DEBUG: First 10 lines of extracted text:")
    for i, line in enumerate(lines[:10]):
        print(f"DEBUG:   {i}: '{line}'")

    # Check PART first (look in first few lines only)
    for i in range(min(5, len(lines))):  # Increased range to 5 lines
        candidate = " ".join(lines[:i+1])
        if PART_PAT.match(candidate):
            result = candidate.title().replace("  ", " ")
            print(f"DEBUG: Found PART: '{result}'")
            return result

    # Check CHAPTER with improved multi-line detection
    print("DEBUG: Checking for chapter...")
    chapter_result = detect_multiline_chapter(lines)
    if chapter_result:
        print(f"DEBUG: Multi-line chapter detected: '{chapter_result}'")
        return chapter_result

    # Check specials with multi-line support
    print("DEBUG: Checking for special sections...")
    for special in SPECIAL_PAT:
        for i in range(min(5, len(lines))):  # Increased range to 5 lines
            candidate = " ".join(lines[:i+1])
            if special.match(candidate):
                result = candidate.title()
                print(f"DEBUG: Found special section: '{result}'")
                return result

    print("DEBUG: No heading found, returning None")
    return None

def detect_multiline_chapter(lines):
    """
    Detect chapter headings that may span multiple lines.
    Handles cases like:
    - "CHAPTER ONE HUNDRED" + "AND NINE"
    - "CHAPTER" + "ONE HUNDRED AND NINE"
    """
    if not lines:
        return None
    
    print("DEBUG: detect_multiline_chapter called")
    
    # Look through first 5 lines for chapter patterns
    for end_line in range(1, min(6, len(lines) + 1)):
        candidate = " ".join(lines[:end_line])
        print(f"DEBUG: Testing candidate ({end_line} lines): '{candidate}'")
        
        # Test if this multi-line candidate matches chapter pattern
        if is_valid_chapter_title(candidate):
            result = candidate.title().replace("  ", " ")
            print(f"DEBUG: Valid chapter found: '{result}'")
            return result
    
    print("DEBUG: No valid chapter found in multi-line detection")
    return None

def is_valid_chapter_title(text):
    """
    Check if the given text is a valid chapter title.
    Supports multi-line chapter titles.
    """
    import re
    
    # Updated pattern to be more flexible with spacing and line breaks
    chapter_patterns = [
        r'^CHAPTER\s+(?:ONE\s+HUNDRED\s+(?:AND\s+)?(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY)?)$',
        r'^CHAPTER\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|SIXTY|SEVENTY|EIGHTY|NINETY)(?:\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE))?$',
        r'^CHAPTER\s+\d+$',  # Numeric chapters
        r'^CHAPTER\s+[IVX]+$',  # Roman numeral chapters
    ]
    
    text_normalized = ' '.join(text.upper().split())  # Normalize spacing
    
    for pattern in chapter_patterns:
        if re.match(pattern, text_normalized):
            print(f"DEBUG: Pattern matched: {pattern}")
            return True
    
    print(f"DEBUG: No pattern matched for: '{text_normalized}'")
    return False

# Alternative approach if the above doesn't work - more aggressive multi-line detection
def is_chapter_heading_improved(lines):
    """
    Improved chapter detection that specifically handles multi-line cases.
    Returns (is_chapter, chapter_title) tuple.
    """
    if not lines:
        return False, None
    
    print("DEBUG: is_chapter_heading_improved called")
    
    # Check if first line starts with "CHAPTER"
    first_line = lines[0].upper().strip()
    if not first_line.startswith('CHAPTER'):
        return False, None
    
    print(f"DEBUG: First line starts with CHAPTER: '{first_line}'")
    
    # Try combining with subsequent lines to form complete chapter title
    for i in range(1, min(4, len(lines) + 1)):  # Check up to 3 additional lines
        combined = " ".join(lines[:i])
        combined_upper = combined.upper().strip()
        
        print(f"DEBUG: Testing combined ({i} lines): '{combined}'")
        
        # Check if this looks like a complete chapter title
        if is_complete_chapter_title(combined_upper):
            result = combined.title().replace("  ", " ")
            print(f"DEBUG: Complete chapter title found: '{result}'")
            return True, result
    
    # If we can't find a complete title, return the first line if it has "CHAPTER"
    if first_line.startswith('CHAPTER'):
        result = first_line.title()
        print(f"DEBUG: Returning partial chapter title: '{result}'")
        return True, result
    
    return False, None

def is_complete_chapter_title(text):
    """Check if the text represents a complete chapter title."""
    # Common complete chapter patterns
    complete_patterns = [
        r'CHAPTER\s+(?:ONE\s+HUNDRED\s+(?:AND\s+)?(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY)?)',
        r'CHAPTER\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|SIXTY|SEVENTY|EIGHTY|NINETY)(?:\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE))?',
        r'CHAPTER\s+\d+',
        r'CHAPTER\s+[IVX]+',
    ]
    
    import re
    for pattern in complete_patterns:
        if re.match(pattern + r'$', text):
            return True
    
    return False

# Also add debug to your OCR function
def ocr_page_debug(page):
    """Run OCR on a PyMuPDF page and return extracted text with debug info."""
    print("DEBUG: Starting OCR...")
    pix = page.get_pixmap(dpi=300)
    img_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_bytes))
    text = pytesseract.image_to_string(img, lang="eng")
    
    print(f"DEBUG: OCR extracted {len(text)} characters")
    print("DEBUG: First 200 characters of OCR text:")
    print(repr(text[:200]))
    
    return text

def extract_page_number(page):
    """Extract printed page number at bottom, fallback to PDF index."""
    text = page.get_text("text")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return page.number + 1
    last_line = lines[-1]
    if last_line.isdigit():
        return int(last_line)
    return page.number + 1

def clean_directory_name(name):
    """Clean a string to be safe for use as directory name."""
    if not name:
        return ""
    
    # First, let's debug what we're getting
    print(f"DEBUG: Original name: '{name}' (length: {len(name)})")
    print(f"DEBUG: Name repr: {repr(name)}")
    
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    print(f"DEBUG: After space replacement: '{name}'")
    
    # Be more specific about what characters to replace
    # Only replace truly problematic filesystem characters
    name = re.sub(r'[<>:"/\\|?*]', '_', name)  # Removed the quotes from the pattern
    print(f"DEBUG: After character replacement: '{name}'")
    
    # Remove multiple consecutive underscores
    name = re.sub(r'_+', '_', name)
    print(f"DEBUG: After underscore cleanup: '{name}'")
    
    # Remove leading/trailing underscores
    name = name.strip('_')
    print(f"DEBUG: Final result: '{name}'")
    
    return name
# ---------- Main Processing ----------

def process_pdf(pdf_path: str, output_root: str, reference_zip_root_name: str, aggressive_ocr: bool = False):
    """
    Process PDF and split into chapters with improved chapter detection.
    Now includes debug logging to help troubleshoot issues.
    """
    root_dup = reference_zip_root_name
    book_base = reference_zip_root_name

    results = []
    
    # Log file for debugging
    debug_log = []
    
    with fitz.open(pdf_path) as doc:
        n = doc.page_count
        debug_log.append(f"Processing PDF with {n} pages")

        current_part = None
        current_chapter = None
        seen_first_content = False

        for i in range(n):
            page = doc[i]
            page_number = extract_page_number(page)
            heading = extract_heading(page, aggressive_ocr)

            debug_info = f"Page {i} (printed: {page_number})"
            
            # ---------------- COVER (first 4 pages) ----------------
            if i < 4:
                cover_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_Cover"
                cover_dir.mkdir(parents=True, exist_ok=True)
                if i == 0:
                    filename = f"{book_base}_Front_Outer.pdf"
                elif i == 1:
                    filename = f"{book_base}_Front_Inner.pdf"
                elif i == 2:
                    filename = f"{book_base}_Back_Inner.pdf"
                elif i == 3:
                    filename = f"{book_base}_Back_Outer.pdf"
                out_file = cover_dir / filename
                save_page_as_pdf(page, out_file)
                results.append({"page": i, "out": str(out_file)})
                debug_log.append(f"{debug_info}: COVER -> {filename}")
                continue

            # ---------------- Detect Headings ----------------
            if heading and heading.upper().startswith("PART"):
                current_part = clean_directory_name(heading.title())
                current_chapter = None
                seen_first_content = True
                debug_log.append(f"{debug_info}: NEW PART detected: '{heading}' -> {current_part}")
                
            elif heading and heading.upper().startswith("CHAPTER"):
                clean_chapter = clean_directory_name(heading.title())
                current_chapter = clean_chapter
                seen_first_content = True
                debug_log.append(f"{debug_info}: NEW CHAPTER detected: '{heading}' -> {current_chapter}")

            # ---------------- Section Assignment ----------------
            if not seen_first_content:
                # After cover but before first part/chapter -> Index
                section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_Index"
                filename = f"{book_base}_Index_Page {i - 3}.pdf"
                section_type = "Index"
            elif current_part and current_chapter:
                # Chapter within a part
                section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_part}" / f"{book_base}_{current_part}_{current_chapter}"
                filename = f"{book_base}_{current_part}_{current_chapter}_Page {page_number}.pdf"
                section_type = f"Part+Chapter: {current_part}/{current_chapter}"
            elif current_chapter and not current_part:
                # Standalone chapter
                section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_chapter}"
                filename = f"{book_base}_{current_chapter}_Page {page_number}.pdf"
                section_type = f"Chapter: {current_chapter}"
            elif current_part:
                # Part page without specific chapter
                section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_{current_part}"
                filename = f"{book_base}_{current_part}_Page {page_number}.pdf"
                section_type = f"Part: {current_part}"
            else:
                # Fallback
                section_dir = Path(output_root) / root_dup / root_dup / f"{book_base}_Back_Index"
                filename = f"{book_base}_Back_Index_Page {page_number}.pdf"
                section_type = "Back Index"

            section_dir.mkdir(parents=True, exist_ok=True)
            out_file = section_dir / filename
            save_page_as_pdf(page, out_file)

            # Log the assignment
            if heading:
                debug_log.append(f"{debug_info}: Heading '{heading}' -> {section_type}")
            else:
                debug_log.append(f"{debug_info}: No heading -> {section_type}")

            results.append({
                "page": i, 
                "out": str(out_file),
                "heading": heading,
                "section": str(section_dir),
                "current_part": current_part,
                "current_chapter": current_chapter
            })

    # Save debug log
    debug_file = Path(output_root) / f"{book_base}_processing_debug.log"
    with open(debug_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(debug_log))
    
    print(f"Debug log saved to: {debug_file}")
    print(f"Processed {len(results)} pages")
    
    # Print summary of detected chapters
    chapters_found = {}
    for result in results:
        if result.get('heading') and 'CHAPTER' in result['heading'].upper():
            chapters_found[result['heading']] = result['section']
    
    if chapters_found:
        print(f"\nDetected {len(chapters_found)} chapters:")
        for chapter, directory in chapters_found.items():
            print(f"  '{chapter}' -> {directory}")
    else:
        print("\nNo chapters detected - check the debug log for details")

    return results

# Additional debugging function that can be called separately
def debug_specific_pages(pdf_path: str, page_numbers: list):
    """Debug specific pages to see what text is extracted and whether headings are detected."""
    print(f"Debugging pages {page_numbers} in {pdf_path}")
    
    with fitz.open(pdf_path) as doc:
        for page_num in page_numbers:
            if page_num >= doc.page_count:
                print(f"Page {page_num} doesn't exist (PDF has {doc.page_count} pages)")
                continue
                
            page = doc[page_num]
            print(f"\n{'='*50}")
            print(f"PAGE {page_num}")
            print(f"{'='*50}")
            
            # Extract text
            text = page.get_text("text")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            
            print("First 15 lines:")
            for i, line in enumerate(lines[:15]):
                print(f"  {i:2d}: '{line}'")
            
            # Test heading detection
            heading = extract_heading(page)
            if heading:
                print(f"\nHEADING DETECTED: '{heading}'")
            else:
                print(f"\nNO HEADING DETECTED")
            
            # Test chapter detection specifically
            is_chapter, chapter_title = is_chapter_heading(lines)
            if is_chapter:
                print(f"CHAPTER DETECTION: YES - '{chapter_title}'")
            else:
                print(f"CHAPTER DETECTION: NO")