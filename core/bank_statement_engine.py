import os
import re
import fitz
import pandas as pd
from datetime import datetime

class BankStatementEngine:
    """
    Core engine for extracting transaction tables from bank statement PDFs.
    Optimized for multi-page Indian bank statements (ICICI, IDFC, HDFC, SBI).
    """
    
    # Common column headers across banks to identify the table start
    HEADER_KEYWORDS = {
        "date": ["DATE", "TXN DATE", "TRANSACTION DATE", "VALUE DATE", "POSTED DATE"],
        "particulars": ["PARTICULARS", "DESCRIPTION", "NARRATION", "REMARKS", "TRANSACTION DETAILS"],
        "chq_ref": ["CHQ", "REF", "CHEQUE", "INSTRUMENT", "REF NO", "UTR", "TRANSACTION ID"],
        "debit": ["DEBIT", "WITHDRAWAL", "AMOUNT (DR)", "DEBIT (DR)", "OUTFLOW", "DR"],
        "credit": ["CREDIT", "DEPOSIT", "AMOUNT (CR)", "CREDIT (CR)", "INFLOW", "CR"],
        "amount": ["TRANSACTION AMOUNT", "AMOUNT", "VALUE"], 
        "type": ["CR/DR", "TYPE"],
        "balance": ["BALANCE", "RUNNING BALANCE", "TOTAL BALANCE", "AVAILABLE BALANCE"]
    }

    @staticmethod
    def parse_statement(file_path: str, password: str = None) -> list:
        """
        Parses a bank statement PDF and returns a list of transaction dictionaries.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            doc = fitz.open(file_path)
            if doc.is_encrypted:
                if password:
                    if not doc.authenticate(password):
                        raise ValueError("Incorrect password provided for PDF.")
                else:
                    raise ValueError("PDF is password protected but no password was provided.")
            
            all_transactions = []
            current_state = "HEADER_SEARCH"
            column_map = {} # Maps column index (or X-lane) to standardized field name
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                # We use words to get precise coordinates
                words = page.get_text("words", sort=True) 
                
                # Group words into lines based on Y coordinate (with some tolerance)
                lines = BankStatementEngine._group_words_by_line(words)
                
                for i, line_words in enumerate(lines):
                    line_text = " ".join([w[4] for w in line_words]).upper()
                    
                    if current_state == "HEADER_SEARCH" or "TOTAL" in line_text or "BALANCE" in line_text:
                        # Try to find the header row
                        found_headers = BankStatementEngine._identify_headers(line_words)
                        if len(found_headers) >= 3:
                            column_map = found_headers
                            current_state = "DATA_EXTRACTION"
                            continue
                    
                    if current_state == "DATA_EXTRACTION":
                        # Detect Footer or End of Statement
                        if any(x in line_text for x in ["CLOSING BALANCE", "TOTAL DEBIT", "STATEMENT SUMMARY", "PAGE:"]):
                            # Note: We don't always stop here for multi-page, but we might skip noise
                            continue
                        
                        # Process Row
                        row_data = BankStatementEngine._process_row(line_words, column_map)
                        if row_data:
                            # If the row has no date but has particulars, it's a continuation
                            if not row_data.get("date") and all_transactions:
                                if row_data.get("particulars"):
                                    all_transactions[-1]["particulars"] += " " + row_data["particulars"]
                            elif row_data.get("date"):
                                all_transactions.append(row_data)

            doc.close()
            
            # Post-processing: Math Validation & Cleaning
            return BankStatementEngine._validate_and_clean(all_transactions)

        except Exception as e:
            raise Exception(f"Bank Parsing Error: {str(e)}")

    @staticmethod
    def _group_words_by_line(words, tolerance=3):
        """Groups PyMuPDF 'words' into lines based on vertical Y coordinate."""
        if not words: return []
        lines = []
        current_line = [words[0]]
        for i in range(1, len(words)):
            # words[i] = (x0, y0, x1, y1, "text", block_no, line_no, word_no)
            if abs(words[i][1] - current_line[0][1]) <= tolerance:
                current_line.append(words[i])
            else:
                lines.append(sorted(current_line, key=lambda x: x[0])) # Sort by X to ensure reading order
                current_line = [words[i]]
        if current_line:
            lines.append(sorted(current_line, key=lambda x: x[0]))
        return lines

    @staticmethod
    def _identify_headers(line_words):
        """Identifies standard columns by checking text against HEADER_KEYWORDS."""
        found = {}
        # Join words to catch multi-word headers like "AVAILABLE BALANCE"
        line_text = " ".join([w[4].upper() for w in line_words])
        
        for field, aliases in BankStatementEngine.HEADER_KEYWORDS.items():
            for alias in aliases:
                if alias in line_text:
                    # Find the word(s) that match this alias to get coordinates
                    # (Simplified: find first word that is part of the alias)
                    for w in line_words:
                        if w[4].upper() in alias or alias in w[4].upper():
                            x_center = (w[0] + w[2]) / 2
                            found[field] = x_center
                            break
        return found

    @staticmethod
    def _process_row(line_words, column_map):
        """Maps line words to columns based on X coordinate lanes."""
        if not column_map: return None
        
        row = {"date": "", "particulars": "", "chq_ref": "", "debit": "", "credit": "", "balance": "", "amount": "", "type": ""}
        
        # Sort column map by X to define lanes
        sorted_lanes = sorted(column_map.items(), key=lambda x: x[1])
        
        # Simple date pattern check for new row start
        has_date = False
        full_text = " ".join([w[4] for w in line_words])
        if re.search(r'\d{1,2}[/\-\s]([A-Za-z]{3}|\d{2})[/\-\s]\d{2,4}', full_text):
            has_date = True

        for w in line_words:
            x_mid = (w[0] + w[2]) / 2
            text = w[4].strip()
            
            # Find the closest matching column lane
            best_field = None
            min_dist = 9999
            for field, x_header in column_map.items():
                dist = abs(x_mid - x_header)
                if dist < min_dist:
                    min_dist = dist
                    best_field = field
            
            # Use distance threshold (e.g., 60 units) to avoid misallocation
            if best_field and min_dist < 60:
                if row[best_field]: row[best_field] += " " + text
                else: row[best_field] = text

        # Handle ICICI-style "Amount" + "DR/CR Type" columns
        if row["amount"] and not (row["debit"] or row["credit"]):
            typ = row["type"].upper()
            if "DR" in typ: row["debit"] = row["amount"]
            elif "CR" in typ: row["credit"] = row["amount"]
            else:
                # Fallback: Check if another column has DR/CR
                full_line = " ".join([w[4].upper() for w in line_words])
                if " DR " in full_line or full_line.endswith(" DR"): row["debit"] = row["amount"]
                elif " CR " in full_line or full_line.endswith(" CR"): row["credit"] = row["amount"]

        # Basic validation: must have at least particulars or date to be interesting
        if not row["particulars"] and not row["date"]:
            return None
            
        return row

    @staticmethod
    def _validate_and_clean(txns):
        """Normalizes numbers, dates and performs running balance audit."""
        cleaned = []
        last_balance = None
        
        for t in txns:
            # Clean numbers
            d = BankStatementEngine._clean_curr(t["debit"])
            c = BankStatementEngine._clean_curr(t["credit"])
            b = BankStatementEngine._clean_curr(t["balance"])
            
            # Audit Math
            remarks = ""
            if last_balance is not None and b:
                expected = round(last_balance + c - d, 2)
                if abs(expected - b) > 0.1:
                    remarks = f"Math Mismatch: Expected {expected}"
            
            cleaned.append({
                "Date": t["date"],
                "Particulars": t["particulars"],
                "Chq/Ref": t["chq_ref"],
                "Debit": d if d > 0 else "",
                "Credit": c if c > 0 else "",
                "Balance": b if b > 0 else "",
                "Validation": remarks
            })
            if b: last_balance = b
            
        return cleaned

    @staticmethod
    def _clean_curr(s):
        if not s: return 0.0
        try:
            # Remove everything except digits and dot
            clean = re.sub(r'[^\d\.]', '', s.replace(',', ''))
            return float(clean) if clean else 0.0
        except:
            return 0.0
