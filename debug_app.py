"""
Debug script to test PDF processing without FastAPI
Run this directly to see what's happening with your PDF
"""

from processing import process_pdf, debug_specific_pages
from pathlib import Path
import sys

def analyze_pdf_structure():
    """Analyze the PDF to understand why text extraction is failing"""
    
    # UPDATE THIS PATH TO YOUR ACTUAL PDF
    pdf_path = "path/to/your/book.pdf"
    
    print("=== PDF STRUCTURE ANALYSIS ===")
    
    if not Path(pdf_path).exists():
        print(f"ERROR: Update the pdf_path in this script to point to your PDF")
        print(f"Looking for: {pdf_path}")
        return
        
    try:
        import fitz
        
        with fitz.open(pdf_path) as doc:
            print(f"PDF Info:")
            print(f"  Total pages: {doc.page_count}")
            print(f"  Metadata: {doc.metadata}")
            print(f"  Encrypted: {doc.is_encrypted}")
            print(f"  PDF version: {doc.pdf_version()}")
            
            # Test a few pages with different extraction methods
            test_pages = [33, 34, 35, 346, 347, 348]
            
            for page_num in test_pages:
                if page_num >= doc.page_count:
                    continue
                    
                print(f"\n{'='*50}")
                print(f"ANALYZING PAGE {page_num}")
                print(f"{'='*50}")
                
                page = doc[page_num]
                
                # Method 1: Simple text extraction
                text_simple = page.get_text("text")
                print(f"Simple text extraction: {len(text_simple)} characters")
                if text_simple.strip():
                    lines = [line.strip() for line in text_simple.splitlines() if line.strip()]
                    print(f"  Non-empty lines: {len(lines)}")
                    print(f"  First few lines:")
                    for i, line in enumerate(lines[:5]):
                        print(f"    {i}: '{line}'")
                else:
                    print("  No text found with simple extraction")
                
                # Method 2: Dictionary extraction (more detailed)
                try:
                    text_dict = page.get_text("dict")
                    blocks = text_dict.get("blocks", [])
                    print(f"Dictionary extraction: {len(blocks)} blocks")
                    
                    text_from_dict = ""
                    for block in blocks[:3]:  # Check first 3 blocks
                        if "lines" in block:
                            for line in block["lines"]:
                                for span in line.get("spans", []):
                                    text_from_dict += span.get("text", "") + " "
                    
                    if text_from_dict.strip():
                        print(f"  Text from dict: '{text_from_dict[:200]}...'")
                    else:
                        print("  No text found in dictionary blocks")
                        
                except Exception as e:
                    print(f"  Dictionary extraction failed: {e}")
                
                # Method 3: Check if page has images (might be scanned)
                try:
                    images = page.get_images()
                    print(f"Images on page: {len(images)}")
                    if images:
                        print("  This might be a scanned/image-based page")
                        
                        # Try OCR on this page if it has images but no text
                        if not text_simple.strip() and images:
                            print("  Attempting OCR...")
                            try:
                                from processing import ocr_page
                                ocr_text = ocr_page(page)
                                if ocr_text.strip():
                                    ocr_lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
                                    print(f"  OCR found {len(ocr_lines)} lines:")
                                    for i, line in enumerate(ocr_lines[:5]):
                                        print(f"    OCR {i}: '{line}'")
                                else:
                                    print("  OCR returned no text")
                            except Exception as ocr_error:
                                print(f"  OCR failed: {ocr_error}")
                                
                except Exception as e:
                    print(f"  Image check failed: {e}")
                    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

def test_pdf_processing():
    """Test the PDF processing with your actual file"""
    
    # UPDATE THESE PATHS TO MATCH YOUR SETUP
    pdf_path = "path/to/your/book.pdf"  # Replace with actual path
    output_root = "test_output"  # This will create a test_output folder
    reference_zip_root_name = "WF_2141_3rd_Degree"  # Or whatever your book name is
    
    print("=== DEBUGGING PDF PROCESSING ===")
    print(f"PDF Path: {pdf_path}")
    print(f"Output: {output_root}")
    print(f"Book Name: {reference_zip_root_name}")
    
    # Check if PDF exists
    if not Path(pdf_path).exists():
        print(f"ERROR: PDF file not found at {pdf_path}")
        print("Please update the pdf_path variable in this script")
        return
    
    try:
        print("\n1. Testing specific pages for chapter detection...")
        # Test pages around where you saw the issue
        debug_specific_pages(pdf_path, [346, 347, 348, 349, 350, 351, 352])
        
        print(f"\n2. Processing full PDF...")
        results = process_pdf(
            pdf_path=pdf_path,
            output_root=output_root,
            reference_zip_root_name=reference_zip_root_name,
            aggressive_ocr=False
        )
        
        print(f"\n3. RESULTS:")
        print(f"   Total pages processed: {len(results)}")
        
        # Show debug log
        debug_log_path = Path(output_root) / f"{reference_zip_root_name}_processing_debug.log"
        if debug_log_path.exists():
            print(f"\n4. DEBUG LOG (last 20 lines):")
            with open(debug_log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines[-20:]:
                    print(f"   {line.strip()}")
        
        # Check what directories were created
        print(f"\n5. CREATED DIRECTORIES:")
        output_path = Path(output_root)
        if output_path.exists():
            for item in output_path.rglob("*"):
                if item.is_dir():
                    print(f"   {item}")
        
        print(f"\n6. SAMPLE FILES:")
        for i, result in enumerate(results[:5]):
            print(f"   Page {result['page']}: {result.get('heading', 'No heading')} -> {result['out']}")
            if i >= 4:
                break
                
        # Show files around the problem area (pages 346-352)
        print(f"\n7. FILES AROUND PROBLEM AREA (pages 346-352):")
        for result in results:
            if 346 <= result['page'] <= 352:
                print(f"   Page {result['page']}: {result.get('heading', 'No heading')} -> {result['out']}")
                
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

def quick_chapter_test():
    """Quick test to see what's being detected on specific pages"""
    
    # UPDATE THIS PATH
    pdf_path = "path/to/your/book.pdf"
    
    print("=== QUICK CHAPTER DETECTION TEST ===")
    
    if not Path(pdf_path).exists():
        print(f"ERROR: Update the pdf_path in this script to point to your PDF")
        return
        
    try:
        # Test the problematic pages
        debug_specific_pages(pdf_path, [346, 347, 348, 349, 350, 351, 352, 353, 354, 355])
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

def simple_text_test():
    """Very simple test to just see if we can extract any text at all"""
    
    # UPDATE THIS PATH
    pdf_path = "path/to/your/book.pdf"
    
    print("=== SIMPLE TEXT EXTRACTION TEST ===")
    
    if not Path(pdf_path).exists():
        print(f"ERROR: PDF not found. Please update the pdf_path variable.")
        print(f"Current path: {pdf_path}")
        return
        
    try:
        import fitz
        
        with fitz.open(pdf_path) as doc:
            print(f"PDF has {doc.page_count} pages")
            
            # Test first few pages
            for i in range(min(5, doc.page_count)):
                page = doc[i]
                text = page.get_text("text")
                
                print(f"\nPage {i}: {len(text)} characters")
                if text.strip():
                    lines = text.splitlines()
                    non_empty_lines = [line for line in lines if line.strip()]
                    print(f"  {len(non_empty_lines)} non-empty lines")
                    print(f"  Sample: '{text[:100]}...'")
                else:
                    print("  NO TEXT FOUND")
                    
            # Test the problematic page (347 from your screenshot)
            if doc.page_count > 347:
                page = doc[347]
                text = page.get_text("text")
                print(f"\nPage 347: {len(text)} characters")
                if text.strip():
                    lines = text.splitlines()
                    non_empty_lines = [line for line in lines if line.strip()]
                    print(f"  {len(non_empty_lines)} non-empty lines")
                    print(f"  Full text: '{text}'")
                else:
                    print("  NO TEXT FOUND on page 347")
                    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Choose test:")
    print("1. Quick chapter detection test")
    print("2. Full PDF processing test") 
    print("3. PDF structure analysis")
    print("4. Simple text extraction test (RECOMMENDED - try this first)")
    
    choice = input("Enter 1, 2, 3, or 4: ").strip()
    
    if choice == "1":
        quick_chapter_test()
    elif choice == "2":
        test_pdf_processing()
    elif choice == "3":
        analyze_pdf_structure()
    elif choice == "4":
        simple_text_test()
    else:
        print("Invalid choice. Running simple text test...")
        simple_text_test()