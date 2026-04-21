"""
PDF Table Extractor Service
Extracts tables from text-based and scanned PDFs.
Uses pdfplumber for text PDFs and pymupdf + pytesseract for scanned PDFs.
"""
import os
import re

# Graceful imports
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import fitz  # pymupdf
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    import pytesseract
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


class PDFTypeDetector:
    """Detects whether a PDF is text-based, scanned/image-based, or mixed."""

    TEXT = "text"
    SCANNED = "scanned"
    MIXED = "mixed"

    @staticmethod
    def detect(pdf_path):
        """Returns PDFTypeDetector.TEXT, SCANNED, or MIXED."""
        if not HAS_FITZ:
            return PDFTypeDetector.TEXT  # Fallback assumption

        doc = fitz.open(pdf_path)
        text_pages = 0
        image_pages = 0

        for page in doc:
            text = page.get_text("text").strip()
            images = page.get_images(full=True)
            if len(text) > 50:
                text_pages += 1
            elif images:
                image_pages += 1
            else:
                # Very little text but also no images — treat as text
                text_pages += 1

        doc.close()

        if text_pages > 0 and image_pages == 0:
            return PDFTypeDetector.TEXT
        elif image_pages > 0 and text_pages == 0:
            return PDFTypeDetector.SCANNED
        else:
            return PDFTypeDetector.MIXED


class ExtractionResult:
    """Holds extraction results with confidence metadata."""

    def __init__(self):
        self.headers = []
        self.rows = []           # list of list[str]
        self.confidence = []     # per-row confidence (0.0 - 1.0)
        self.warnings = []       # list of warning strings
        self.pdf_type = ""
        self.page_count = 0
        self.total_rows = 0
        self.ocr_text = ""       # Raw OCR text if applicable

    def add_row(self, row, conf=1.0):
        self.rows.append(row)
        self.confidence.append(conf)
        self.total_rows += 1

    def get_clean_rows(self, threshold=0.5):
        """Returns rows with confidence above threshold."""
        return [r for r, c in zip(self.rows, self.confidence) if c >= threshold]

    def get_exception_rows(self, threshold=0.5):
        """Returns rows with confidence below threshold (for review)."""
        return [r for r, c in zip(self.rows, self.confidence) if c < threshold]


class PDFTableExtractor:
    """Main extraction engine supporting multiple modes."""

    MODE_FAST = "fast"
    MODE_ACCURATE = "accurate"
    MODE_OCR = "ocr"
    MODE_BANK = "bank_statement"

    @staticmethod
    def extract(pdf_path, mode="accurate", pages=None, progress_callback=None):
        """
        Extract tables from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            mode: Extraction mode (fast, accurate, ocr, bank_statement)
            pages: Optional list of page numbers (0-based) or None for all
            progress_callback: Optional callback(percent) for progress updates
            
        Returns:
            ExtractionResult object
        """
        result = ExtractionResult()

        # Detect PDF type
        result.pdf_type = PDFTypeDetector.detect(pdf_path)

        if mode == PDFTableExtractor.MODE_OCR or result.pdf_type == PDFTypeDetector.SCANNED:
            return PDFTableExtractor._extract_ocr(pdf_path, result, pages, progress_callback)
        else:
            return PDFTableExtractor._extract_text(pdf_path, result, mode, pages, progress_callback)

    @staticmethod
    def _extract_text(pdf_path, result, mode, pages, progress_callback):
        """Extract tables from text-based PDFs using pdfplumber."""
        if not HAS_PDFPLUMBER:
            result.warnings.append("pdfplumber not installed. Install via: pip install pdfplumber")
            return result

        with pdfplumber.open(pdf_path) as pdf:
            result.page_count = len(pdf.pages)
            target_pages = pages if pages else range(len(pdf.pages))

            for i, page_idx in enumerate(target_pages):
                if page_idx >= len(pdf.pages):
                    continue

                page = pdf.pages[page_idx]

                # Table extraction settings based on mode
                if mode == PDFTableExtractor.MODE_FAST:
                    settings = {"vertical_strategy": "text", "horizontal_strategy": "text"}
                else:  # accurate
                    settings = {
                        "vertical_strategy": "lines_strict",
                        "horizontal_strategy": "lines_strict",
                        "snap_tolerance": 5,
                        "join_tolerance": 5,
                    }

                tables = page.extract_tables(table_settings=settings)

                if not tables and mode == PDFTableExtractor.MODE_ACCURATE:
                    # Fallback to text strategy if strict lines find nothing
                    settings = {"vertical_strategy": "text", "horizontal_strategy": "text"}
                    tables = page.extract_tables(table_settings=settings)

                for table in tables:
                    for row_idx, row in enumerate(table):
                        cleaned = [str(cell).strip() if cell else "" for cell in row]

                        # Skip completely empty rows
                        if not any(cleaned):
                            continue

                        # First meaningful row as header (if we don't have one yet)
                        if not result.headers and row_idx == 0:
                            result.headers = cleaned
                            continue

                        # Calculate confidence based on non-empty cells
                        non_empty = sum(1 for c in cleaned if c)
                        total = len(cleaned) if cleaned else 1
                        conf = non_empty / total

                        result.add_row(cleaned, conf)

                # If no tables found on this page, try extracting text as lines
                if not tables:
                    text = page.extract_text()
                    if text:
                        for line in text.split("\n"):
                            line = line.strip()
                            if line:
                                # Split by multiple spaces (common table separator)
                                cells = re.split(r'\s{2,}', line)
                                if len(cells) > 1:
                                    result.add_row(cells, 0.6)
                                else:
                                    result.add_row([line], 0.3)

                if progress_callback:
                    pct = int(((i + 1) / len(target_pages)) * 100)
                    progress_callback(pct)

        return result

    @staticmethod
    def _preprocess_image(img):
        """Preprocess image for better OCR accuracy."""
        # 1. Grayscale
        img = img.convert('L')
        # 2. Enhance Contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        # 3. Sharpness
        img = img.filter(ImageFilter.SHARPEN)
        # 4. Thresholding (Binarization)
        img = img.point(lambda p: p > 128 and 255)
        return img

    @staticmethod
    def _extract_ocr(pdf_path, result, pages, progress_callback):
        """Extract tables from scanned PDFs using OCR."""
        if not HAS_FITZ:
            result.warnings.append("pymupdf not installed. Cannot process scanned PDFs.")
            return result

        if not HAS_OCR:
            result.warnings.append("pytesseract/Pillow not installed. Cannot perform OCR.")
            return result

        doc = fitz.open(pdf_path)
        result.page_count = len(doc)
        target_pages = pages if pages is not None else range(len(doc))

        full_ocr_text = []

        for i, page_idx in enumerate(target_pages):
            if page_idx >= len(doc):
                continue

            page = doc[page_idx]

            # Render page to high-DPI image for OCR (300 DPI)
            zoom = 300 / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")

            import io
            img = Image.open(io.BytesIO(img_data))
            
            # Apply Preprocessing
            img = PDFTableExtractor._preprocess_image(img)

            # Use pytesseract with PSM 6 (single uniform block of text)
            try:
                text = pytesseract.image_to_string(img, config='--psm 6')
                if text:
                    full_ocr_text.append(f"--- Page {page_idx + 1} ---\n{text}")
            except Exception as e:
                result.warnings.append(f"OCR failed on page {page_idx + 1}: {str(e)}")
                continue

            if text:
                lines = text.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    # Split by multiple spaces
                    cells = re.split(r'\s{2,}', line)
                    if len(cells) > 1:
                        if not result.headers:
                            result.headers = cells
                        else:
                            result.add_row(cells, 0.5)  # OCR has lower confidence
                    else:
                        result.add_row([line], 0.3)

            if progress_callback:
                pct = int(((i + 1) / len(target_pages)) * 100)
                progress_callback(pct)

        result.ocr_text = "\n".join(full_ocr_text)
        doc.close()
        return result

    @staticmethod
    def get_page_count(pdf_path):
        """Returns the number of pages in a PDF."""
        if HAS_FITZ:
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        elif HAS_PDFPLUMBER:
            with pdfplumber.open(pdf_path) as pdf:
                return len(pdf.pages)
        return 0
