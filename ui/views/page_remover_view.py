import customtkinter as ctk
from ui.components import DragDropArea, SmartNamingFrame
from utils.file_manager import FileManager
from core.pdf_engine import PDFEngine
import threading
from ui.theme import Theme
import os

class PageRemoverView(ctk.CTkFrame):
    def __init__(self, master, app_window, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app_window
        self.pdf_file = None
        
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        lbl_hdr = ctk.CTkLabel(self, text="Page Remover", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=24, weight="bold"))
        lbl_hdr.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 20))
        
        left_panel = ctk.CTkFrame(self, fg_color="transparent")
        left_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left_panel.grid_rowconfigure(2, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)
        
        self.dnd_area = DragDropArea(left_panel, title="Drop 1 PDF Here", on_drop_callback=self.on_file_dropped, height=120)
        self.dnd_area.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        self.lbl_selected = ctk.CTkLabel(left_panel, text="No PDF selected", text_color=Theme.TEXT_MUTED, font=(Theme.FONT_FAMILY, 13))
        self.lbl_selected.grid(row=1, column=0, sticky="w", pady=(0, 10))
        
        tools_frame = ctk.CTkFrame(left_panel, fg_color=Theme.BG_SECONDARY, corner_radius=Theme.CORNER_RADIUS,
                                   border_width=Theme.BORDER_WIDTH, border_color=Theme.BORDER_COLOR)
        tools_frame.grid(row=2, column=0, sticky="nsew")
        
        # Action selector
        ctk.CTkLabel(tools_frame, text="Enter Pages to Delete (e.g. 2, 5, 7 or 1-3):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(20, 10))
        self.ent_pages = ctk.CTkEntry(tools_frame, placeholder_text="Pages to delete", width=300)
        self.ent_pages.pack(anchor="w", padx=20, pady=(0, 20))
        
        right_panel = ctk.CTkFrame(self, fg_color="transparent")
        right_panel.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        
        self.naming_frame = SmartNamingFrame(right_panel)
        self.naming_frame.pack(fill="x", pady=(0, 20))
        
        self.btn_process = ctk.CTkButton(right_panel, text="Remove Pages", height=44, corner_radius=10,
                                         fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                                         font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=15, weight="bold"), 
                                         command=self.start_process)
        self.btn_process.pack(fill="x", pady=10)
        
        self.progress = ctk.CTkProgressBar(right_panel, progress_color=Theme.ACCENT_BLUE)
        self.progress.pack(fill="x", pady=10)
        self.progress.set(0)
            
    def on_file_dropped(self, files):
        pdf_files = [f for f in files if f.lower().endswith('.pdf')]
        if pdf_files:
            self.pdf_file = pdf_files[0]
            self.lbl_selected.configure(text=f"Selected: {os.path.basename(self.pdf_file)}", text_color="white")
        else:
            self.app.show_toast("Error", "Please drop a valid PDF file.", is_error=True)
            
    def _parse_pages(self, page_str):
        pages = set()
        for part in page_str.split(','):
            part = part.strip()
            if not part: continue
            if '-' in part:
                try:
                    start, end = part.split('-')
                    pages.update(range(int(start), int(end) + 1))
                except Exception:
                    continue
            else:
                try:
                    pages.add(int(part))
                except Exception:
                    continue
        return sorted(list(pages))
            
    def start_process(self):
        if not self.pdf_file:
            self.app.show_toast("Error", "Please select a PDF file first.", is_error=True)
            return

        pages_str = self.ent_pages.get()
        pages = self._parse_pages(pages_str)
        if not pages:
            self.app.show_toast("Error", "Please enter valid page numbers to delete.", is_error=True)
            return

        naming_data = self.naming_frame.get_data()
        try:
            output_path = FileManager.generate_simple_output_path(
                output_dir=naming_data.get("output_dir", ""),
                output_filename=naming_data.get("output_filename", "")
            )
        except ValueError as e:
            self.app.show_toast("Error", str(e), is_error=True)
            return
            
        self.btn_process.configure(state="disabled", text="Processing...")
        threading.Thread(target=self._process_thread, args=(output_path, pages), daemon=True).start()
        
    def _process_thread(self, output_path, pages):
        try:
            PDFEngine.remove_pages(self.pdf_file, output_path, pages)
            msg = f"Pages removed successfully!\nSaved to:\n{output_path}"
                
            self.after(500, lambda: self._on_success(msg))
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))
            
    def _on_success(self, msg):
        self.btn_process.configure(state="normal", text="Remove Pages")
        self.app.show_toast("Success", msg)
        
    def _on_error(self, error_msg):
        self.btn_process.configure(state="normal", text="Remove Pages")
        self.app.show_toast("Process Failed", error_msg, is_error=True)
