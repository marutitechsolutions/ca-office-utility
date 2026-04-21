import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk

from ui.theme import Theme
from ui.components import DragDropArea
from services.bank_statement_service import BankStatementService

class BankStatementView(ctk.CTkFrame):
    def __init__(self, master, app_window, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app_window = app_window
        
        self.files_to_process = []
        self.file_map = {} # basename -> full_path
        self.processed_results = [] # List of processing result dicts
        self.is_processing = False
        self.passwords = {} # filename -> password
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._setup_header()
        self._setup_drag_drop()
        
        self.columns = ("Filename", "Status", "Txn Count", "Starting Bal", "Closing Bal", "Remarks")
        self._setup_grid_area()
        self._setup_footer()

    def _setup_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        
        title = ctk.CTkLabel(header_frame, text="Bank Statement Converter", 
                             font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=24, weight="bold"))
        title.pack(side="left")
        
        desc = ctk.CTkLabel(header_frame, text="Convert any Bank PDF to professional Excel with 100% accuracy", 
                            text_color=Theme.TEXT_MUTED, font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=14, weight="bold"))
        desc.pack(side="left", padx=15, pady=(5,0))

    def _setup_drag_drop(self):
        self.dnd_area = DragDropArea(self, on_drop_callback=self._handle_new_files, height=100)
        self.dnd_area.grid(row=1, column=0, sticky="ew", pady=(0, 20), padx=Theme.PADDING)

    def _setup_grid_area(self):
        self.grid_frame = ctk.CTkFrame(self, fg_color=Theme.BG_SECONDARY, corner_radius=Theme.CORNER_RADIUS)
        self.grid_frame.grid(row=2, column=0, sticky="nsew", padx=Theme.PADDING)
        self.grid_frame.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", 
                        background=Theme.BG_PRIMARY,
                        foreground=Theme.TEXT_PRIMARY,
                        rowheight=35,
                        fieldbackground=Theme.BG_PRIMARY,
                        borderwidth=0,
                        font=(Theme.FONT_FAMILY, 10))
        style.map('Treeview', background=[('selected', Theme.ACCENT_BLUE)])
        
        style.configure("Treeview.Heading", 
                        background=Theme.BG_SECONDARY, 
                        foreground=Theme.TEXT_PRIMARY, 
                        font=(Theme.FONT_FAMILY, 11, "bold"),
                        borderwidth=1,
                        relief="flat")

        self.tree = ttk.Treeview(self.grid_frame, columns=self.columns, show="headings", selectmode="extended")
        
        widths = {
            "Filename": 250, "Status": 100, "Txn Count": 100, "Starting Bal": 120, "Closing Bal": 120, "Remarks": 300
        }
        
        for col in self.columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=widths.get(col, 100), anchor="w" if col in ["Filename", "Remarks"] else "center")
            
        scrollbar_y = ttk.Scrollbar(self.grid_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar_y.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        scrollbar_y.grid(row=0, column=1, sticky="ns", pady=10)
        
        self.tree.tag_configure("Failed", background="#4a1515")
        self.tree.tag_configure("Success", background="#124021")

    def _setup_footer(self):
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.grid(row=3, column=0, sticky="ew", pady=20, padx=Theme.PADDING)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ctk.CTkProgressBar(footer_frame, variable=self.progress_var, width=300, height=10, 
                                               progress_color=Theme.ACCENT_GREEN)
        self.progress_bar.pack(side="left", padx=(0, 20))
        self.progress_bar.set(0)
        
        self.status_label = ctk.CTkLabel(footer_frame, text="Ready", text_color=Theme.TEXT_MUTED)
        self.status_label.pack(side="left")
        
        self.btn_export = ctk.CTkButton(footer_frame, text="Export consolidated Excel", width=180, 
                                        fg_color=Theme.ACCENT_GREEN, hover_color=Theme.ACTIVATION_HOVER,
                                        command=self._export_to_excel)
        self.btn_export.pack(side="right")
        
        self.btn_clear_all = ctk.CTkButton(footer_frame, text="Clear All", width=80, 
                                           fg_color="transparent", border_width=1, text_color=Theme.TEXT_PRIMARY,
                                           command=self._clear_all)
        self.btn_clear_all.pack(side="right", padx=10)

        self.btn_process = ctk.CTkButton(footer_frame, text="Start Conversion", width=140, 
                                          fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                                          command=self._start_processing)
        self.btn_process.pack(side="right")

    def _handle_new_files(self, files):
        if self.is_processing: return
        added = 0
        existing = [self.tree.set(item, "Filename") for item in self.tree.get_children()]
        
        for f in files:
            basename = os.path.basename(f)
            if basename not in existing:
                if f.lower().endswith('.pdf'):
                    self.files_to_process.append(f)
                    self.file_map[basename] = f
                    self.tree.insert("", "end", values=(basename, "Pending", "-", "-", "-", "Click Start to begin"))
                    added += 1
        
        if added > 0:
            self.status_label.configure(text=f"Added {added} statements.")

    def _start_processing(self):
        pending = [item for item in self.tree.get_children() if self.tree.set(item, "Status") == "Pending"]
        if not pending:
            messagebox.showinfo("No Files", "Please add new PDF files first.")
            return
            
        self.is_processing = True
        self.btn_process.configure(state="disabled")
        self.btn_export.configure(state="disabled")
        self.status_label.configure(text="Converting statements...")
        
        file_paths = [self.file_map[self.tree.set(item, "Filename")] for item in pending]
        threading.Thread(target=self._proc_thread, args=(file_paths, pending), daemon=True).start()

    def _proc_thread(self, file_paths, items):
        results = BankStatementService.process_files(file_paths, self.passwords)
        self.app_window.after(0, lambda r=results, it=items: self._update_results(r, it))

    def _update_results(self, results, items):
        self.processed_results.extend(results)
        # Match results back to tree items
        for res in results:
            for item in items:
                if self.tree.set(item, "Filename") == res["filename"]:
                    data = res["data"]
                    start_bal = data[0]["Balance"] if data else "-"
                    end_bal = data[-1]["Balance"] if data else "-"
                    
                    self.tree.item(item, values=(
                        res["filename"], res["status"], res["count"], 
                        start_bal, end_bal, res["remarks"]
                    ), tags=(res["status"],))
                    break
        
        self.is_processing = False
        self.btn_process.configure(state="normal")
        self.btn_export.configure(state="normal")
        self.status_label.configure(text="Conversion complete.")
        self.progress_bar.set(1.0)

    def _export_to_excel(self):
        if not self.processed_results:
            messagebox.showinfo("No Data", "Please process some statements first.")
            return
            
        output_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            title="Save Bank Excel", initialfile=f"Bank_Statement_Summary_{datetime.now().strftime('%d%m%Y')}.xlsx"
        )
        if not output_path: return
        
        success = BankStatementService.export_to_excel(self.processed_results, output_path)
        if success:
            messagebox.showinfo("Success", f"Excel exported successfully!\nPath: {output_path}")
            if hasattr(self.app_window, "show_toast"):
                self.app_window.show_toast("SUCCESS", "Bank Statement exported.")
        else:
            messagebox.showerror("Export Failed", "No successful data items found to export.")

    def _clear_all(self):
        if self.is_processing: return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.files_to_process.clear()
        self.file_map.clear()
        self.processed_results.clear()
        self.progress_bar.set(0)
        self.status_label.configure(text="Ready")
