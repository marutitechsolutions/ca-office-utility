import os
import pandas as pd
from datetime import datetime
from core.bank_statement_engine import BankStatementEngine

class BankStatementService:
    @staticmethod
    def process_files(file_paths: list, password_map: dict = None) -> list:
        """
        Processes multiple bank statements and returns a consolidated status list.
        Each item in the list represents a processed physical document.
        """
        all_results = []
        for file_path in file_paths:
            filename = os.path.basename(file_path)
            password = password_map.get(filename) if password_map else None
            
            try:
                transactions = BankStatementEngine.parse_statement(file_path, password)
                all_results.append({
                    "filename": filename,
                    "status": "Success",
                    "count": len(transactions),
                    "data": transactions,
                    "remarks": ""
                })
            except Exception as e:
                all_results.append({
                    "filename": filename,
                    "status": "Failed",
                    "count": 0,
                    "data": [],
                    "remarks": str(e)
                })
        return all_results

    @staticmethod
    def export_to_excel(processed_results, export_path):
        """
        Consolidates all successful extractions into a single formatted Excel file.
        """
        if not processed_results:
            return False

        # Prepare a list of all data rows across all files
        consolidated_data = []
        for res in processed_results:
            if res["status"] == "Success":
                # Add a Source column to keep track of the file
                for row in res["data"]:
                    row["Source File"] = res["filename"]
                    consolidated_data.append(row)

        if not consolidated_data:
            return False

        df = pd.DataFrame(consolidated_data)
        
        # Ensure correct column order
        cols = ["Date", "Particulars", "Chq/Ref", "Debit", "Credit", "Balance", "Validation", "Source File"]
        df = df[cols]

        # Use XlsxWriter for professional styling
        writer = pd.ExcelWriter(export_path, engine='xlsxwriter')
        df.to_excel(writer, index=False, sheet_name='Bank Statement')
        
        workbook  = writer.book
        worksheet = writer.sheets['Bank Statement']

        # Formatters
        header_fmt = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#D7E4BC',
            'border': 1
        })
        
        num_fmt = workbook.add_format({'num_format': '#,##0.00'})
        date_fmt = workbook.add_format({'align': 'left'})
        
        # Apply header format
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            
        # Set column widths
        worksheet.set_column('A:A', 12, date_fmt) # Date
        worksheet.set_column('B:B', 50)           # Particulars
        worksheet.set_column('C:C', 15)           # Chq/Ref
        worksheet.set_column('D:F', 15, num_fmt)  # Debit, Credit, Balance
        worksheet.set_column('G:G', 30)           # Validation
        worksheet.set_column('H:H', 25)           # Source File

        # Freeze the top row
        worksheet.freeze_panes(1, 0)
        
        writer.close()
        return True
