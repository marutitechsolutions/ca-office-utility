"""
Bank Statement Parser Service
Parses bank statements into normalized transaction tables.
Supports multiple Indian bank formats via modular parser architecture.
"""
import re
import os
import pdfplumber
import traceback
from datetime import datetime
from services.pdf_table_extractor import PDFTableExtractor

# ─── Bank Profile Definitions ────────────────────────────────────────────────

BANK_PROFILES = {
    "sbi": {"name": "State Bank of India", "keywords": ["sbi", "state bank"], "ifsc": ["sbin"], "date_formats": ["%d/%m/%Y", "%d-%b-%Y", "%d-%m-%Y"]},
    "hdfc": {"name": "HDFC Bank", "keywords": ["hdfc"], "ifsc": ["hdfc"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "icici": {"name": "ICICI Bank", "keywords": ["icici", "accstmtdownloadreport"], "ifsc": ["icic"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d"]},
    "kotak": {"name": "Kotak Mahindra Bank", "keywords": ["kotak", "kkbk"], "ifsc": ["kkbk"], "date_formats": ["%d-%m-%Y", "%d %b %Y", "%d/%m/%Y", "%d-%b-%Y"]},
    "axis": {"name": "Axis Bank", "keywords": ["axis"], "ifsc": ["utib"], "date_formats": ["%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y"]},
    "bob": {"name": "Bank of Baroda", "keywords": ["bob", "barb"], "ifsc": ["barb"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "au": {"name": "AU Small Finance Bank", "keywords": ["au small finance", "au bank", "aubl"], "ifsc": ["aubl"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d-%b-%Y", "%Y-%m-%d"]},
    "federal": {"name": "Federal Bank", "keywords": ["federal"], "ifsc": ["fdrl"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "idfc": {"name": "IDFC First Bank", "keywords": ["idfc"], "ifsc": ["idfb"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "yes": {"name": "YES Bank", "keywords": ["yes bank"], "ifsc": ["yesb"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "indusind": {"name": "IndusInd Bank", "keywords": ["indusind"], "ifsc": ["indb"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "canara": {"name": "Canara Bank", "keywords": ["canara"], "ifsc": ["cnrb"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "pnb": {"name": "Punjab National Bank", "keywords": ["pnb"], "ifsc": ["punb"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "union": {"name": "Union Bank of India", "keywords": ["union bank"], "ifsc": ["ubin"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "idbi": {"name": "IDBI Bank", "keywords": ["idbi"], "ifsc": ["ibkl"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "standard_chartered": {"name": "Standard Chartered Bank", "keywords": ["standard chartered"], "ifsc": ["scbl"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "hsbc": {"name": "HSBC Bank", "keywords": ["hsbc"], "ifsc": ["hsbc"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "citi": {"name": "Citibank", "keywords": ["citi"], "ifsc": ["citi"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "rbl": {"name": "RBL Bank", "keywords": ["rbl"], "ifsc": ["ratn"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "karur_vysya": {"name": "Karur Vysya Bank", "keywords": ["kvb"], "ifsc": ["kvbl"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "south_indian": {"name": "South Indian Bank", "keywords": ["south indian"], "ifsc": ["sibk"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "dbs": {"name": "DBS Bank India", "keywords": ["dbs"], "ifsc": ["dbss"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "bandhan": {"name": "Bandhan Bank", "keywords": ["bandhan"], "ifsc": ["bdbl"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "equitas": {"name": "Equitas Small Finance Bank", "keywords": ["equitas"], "ifsc": ["esfb"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "ujjivan": {"name": "Ujjivan Small Finance Bank", "keywords": ["ujjivan"], "ifsc": ["ujjv"], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"]},
    "generic": {"name": "Generic / Unknown Bank", "keywords": [], "ifsc": [], "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d"]},
}

class BankParserFactory:
    """Factory to provide the correct parser for a given bank."""
    @staticmethod
    def get_parser(bank_code, profile):
        from services.bank_parsers import KotakParser, AUParser, ICICIParser, GenericBankParser
        parsers = {
            "kotak": KotakParser,
            "au": AUParser,
            "icici": ICICIParser,
        }
        parser_cls = parsers.get(bank_code, GenericBankParser)
        return parser_cls(profile)

class StatementResult:
    """Holds parsed bank statement results."""
    DEFAULT_HEADERS = ["Date", "Narration", "Ref/Cheque No", "Debit", "Credit", "Balance"]

    def __init__(self):
        self.bank_name = ""
        self.bank_code = ""
        self.transactions = []  # list of StatementTransaction
        self.warnings = []
        self.processed_pages = []
        self.skipped_pages = []
        self.custom_headers = None
        self.original_pdf_path = None
        self.needs_password = False

    @property
    def headers(self):
        return self.custom_headers if self.custom_headers else self.DEFAULT_HEADERS

    def to_rows(self):
        return [t.to_list(self.headers) for t in self.transactions]

    def get_clean_transactions(self, threshold=0.5):
        """Returns transactions with confidence above threshold."""
        return [t for t in self.transactions if t.confidence >= threshold]

    def get_exception_transactions(self, threshold=0.5):
        """Returns transactions for review."""
        return [t for t in self.transactions if t.confidence < threshold]

class BankStatementParser:
    """Parses bank statement PDFs into structured transaction data."""

    @staticmethod
    def get_available_banks():
        """Returns list of (code, name) tuples for UI dropdown."""
        return [(code, p["name"]) for code, p in BANK_PROFILES.items()]

    @staticmethod
    def detect_bank(pdf_path, debug_callback=None):
        """Auto-detect bank from PDF text using confidence scoring."""
        try:
            filename = os.path.basename(pdf_path).lower()
            scores = {code: 0 for code in BANK_PROFILES if code != "generic"}
            
            with pdfplumber.open(pdf_path) as pdf:
                text = ""
                for page in pdf.pages[:3]:
                    t = page.extract_text()
                    if t: text += t.lower() + " "
                
                # Fast OCR Fallback on Page 1 if text is basically empty
                if len(text.strip()) < 50:
                    try:
                        from services.pdf_table_extractor import pytesseract
                        ocr_text = pytesseract.image_to_string(pdf.pages[0].to_image(resolution=150).original)
                        text += ocr_text.lower()
                    except: pass

            for code, profile in BANK_PROFILES.items():
                if code == "generic": continue
                name = profile["name"].lower()
                
                # Filename check
                if (len(code) > 2 and code in filename) or name in filename: 
                    scores[code] += 15
                elif len(code) <= 2:
                    # Word boundary check for short codes like 'au'
                    if re.search(rf'\b{code}\b', filename):
                        scores[code] += 15
                
                # High-confidence filename match for ICICI (Lowered boost)
                if code == "icici" and "accstmtdownloadreport" in filename:
                    scores[code] += 10
                
                # Text keywords
                for kw in profile.get("keywords", []):
                    if kw in text: scores[code] += 8
                
                # IFSC code (high confidence)
                for ifsc in profile.get("ifsc", []):
                    if ifsc in text: scores[code] += 20
                        
            # Log scores for debugging if callback provided
            if debug_callback:
                top_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
                debug_callback(f"Top Scores: {top_scores}")

            best_bank = "generic"
            best_score = 0
            for code, score in scores.items():
                if score > best_score:
                    best_score = score
                    best_bank = code
            return best_bank if best_score >= 5 else "generic"
        except Exception as e:
            if debug_callback: debug_callback(f"Bank Detection Error: {e}")
            return "generic"

    @staticmethod
    def parse(pdf_path, bank_code=None, password=None, progress_callback=None, debug_callback=None):
        """Main entry point for bank statement parsing."""
        result = StatementResult()
        result.original_pdf_path = pdf_path
        
        # 1. Detection
        if not bank_code or bank_code == "generic":
            bank_code = BankStatementParser.detect_bank(pdf_path, debug_callback=debug_callback)
        
        profile = BANK_PROFILES.get(bank_code, BANK_PROFILES["generic"])
        if debug_callback:
            debug_callback(f"Detected Bank: {profile['name']} ({bank_code})")
        
        # 2. Check for Password
        total_pages = 0
        try:
            with pdfplumber.open(pdf_path, password=password) as pdf:
                total_pages = len(pdf.pages)
        except Exception as e:
            if "password" in str(e).lower():
                result.needs_password = True
                return result
            if debug_callback: debug_callback(f"Extraction Error: {str(e)}")
            return result

        # 3. Modular Extraction
        parser = BankParserFactory.get_parser(bank_code, profile)
        try:
            final_pages = list(range(total_pages))
            transactions = parser.parse(pdf_path, pages=final_pages, debug_callback=debug_callback)
            
            # Fallback for specialized parser returning nothing
            if not transactions and bank_code != "generic":
                if debug_callback: debug_callback(f"Specialized parser ({bank_code}) returned 0 rows. Falling back to GenericBankParser...")
                from services.bank_parsers import GenericBankParser
                generic_parser = GenericBankParser(BANK_PROFILES["generic"])
                transactions = generic_parser.parse(pdf_path, pages=final_pages, debug_callback=debug_callback)
                if transactions:
                    bank_code = "generic" # Update for headers
                    profile = BANK_PROFILES["generic"]
                    parser = generic_parser
            
            result.transactions = transactions
            result.custom_headers = parser.custom_headers if parser.custom_headers else StatementResult.DEFAULT_HEADERS
            result.processed_pages = [p + 1 for p in final_pages]
            result.bank_name = profile["name"]
            result.bank_code = bank_code
        except Exception as e:
            if debug_callback: debug_callback(f"Parser Error: {traceback.format_exc()}")
            
        return result
