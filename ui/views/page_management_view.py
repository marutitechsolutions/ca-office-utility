import customtkinter as ctk
from ui.components import DragDropArea, FileListFrame, SmartNamingFrame
from utils.file_manager import FileManager
from core.pdf_engine import PDFEngine
import threading
from ui.theme import Theme

class PageManagementView(ctk.CTkFrame):
    def __init__(self, master, app_window, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app_window
        
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        lbl_hdr = ctk.CTkLabel(self, text="Page Management", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=24, weight="bold"))
        lbl_hdr.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 20))
        
        # Left Panel
        left_panel = ctk.CTkFrame(self, fg_color="transparent")
        left_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left_panel.grid_rowconfigure(2, weight=1) # Adjusted row for tools_frame
        left_panel.grid_columnconfigure(0, weight=1)
        
        self.dnd_area = DragDropArea(left_panel, title="Drag & Drop 1 PDF Here", on_drop_callback=self.on_files_dropped)
        self.dnd_area.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        self.lbl_selected = ctk.CTkLabel(left_panel, text="No PDF selected", text_color=Theme.TEXT_MUTED, font=(Theme.FONT_FAMILY, 13))
        self.lbl_selected.grid(row=1, column=0, sticky="w", pady=(0, 10))
        
        tools_frame = ctk.CTkFrame(left_panel, fg_color=Theme.BG_SECONDARY, corner_radius=Theme.CORNER_RADIUS,
                                   border_width=Theme.BORDER_WIDTH, border_color=Theme.BORDER_COLOR)
        tools_frame.grid(row=2, column=0, sticky="nsew")
        tools_frame.grid_rowconfigure(0, weight=1)
        tools_frame.grid_columnconfigure(0, weight=1)
        
        self.file_list = FileListFrame(tools_frame)
        self.file_list.grid(row=0, column=0, sticky="nsew", padx=Theme.PADDING, pady=Theme.PADDING)
        
        # Right Panel
        right_panel = ctk.CTkFrame(self, fg_color="transparent")
        right_panel.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        
        action_frame = ctk.CTkFrame(right_panel, fg_color=Theme.BG_SECONDARY, corner_radius=Theme.CORNER_RADIUS,
                                    border_width=Theme.BORDER_WIDTH, border_color=Theme.BORDER_COLOR)
        action_frame.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(action_frame, text="Management Action:", font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        self.action_var = ctk.StringVar(value="split")
        
        rb_split = ctk.CTkRadioButton(action_frame, text="Split all pages to individual files", variable=self.action_var, value="split", command=self._on_action_change,
                                      font=ctk.CTkFont(family=Theme.FONT_FAMILY), text_color=Theme.TEXT_COLOR)
        rb_split.pack(anchor="w", padx=20, pady=5)
        
        rb_extract = ctk.CTkRadioButton(action_frame, text="Extract specific pages", variable=self.action_var, value="extract", command=self._on_action_change,
                                        font=ctk.CTkFont(family=Theme.FONT_FAMILY), text_color=Theme.TEXT_COLOR)
        rb_extract.pack(anchor="w", padx=20, pady=5)
        
        rb_remove = ctk.CTkRadioButton(action_frame, text="Remove specific pages", variable=self.action_var, value="remove", command=self._on_action_change,
                                       font=ctk.CTkFont(family=Theme.FONT_FAMILY), text_color=Theme.TEXT_COLOR)
        rb_remove.pack(anchor="w", padx=20, pady=5)
        
        rb_rotate = ctk.CTkRadioButton(action_frame, text="Rotate pages (+90 deg)", variable=self.action_var, value="rotate", command=self._on_action_change,
                                       font=ctk.CTkFont(family=Theme.FONT_FAMILY), text_color=Theme.TEXT_COLOR)
        rb_rotate.pack(anchor="w", padx=20, pady=5)
        
        self.param_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
        self.param_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        self.lbl_param = ctk.CTkLabel(self.param_frame, text="", font=ctk.CTkFont(family=Theme.FONT_FAMILY))
        self.lbl_param.grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        self.ent_param = ctk.CTkEntry(self.param_frame, placeholder_text="e.g. 1, 3, 5-7",
                                      corner_radius=Theme.CORNER_RADIUS, border_color=Theme.BORDER_COLOR, border_width=Theme.BORDER_WIDTH,
                                      font=ctk.CTkFont(family=Theme.FONT_FAMILY))
        self.ent_param.grid(row=1, column=0, sticky="ew")
        
        self.param_frame.grid_columnconfigure(0, weight=1)
        
        # Initialize visibility
        self._on_action_change()
        
        self.naming_frame = SmartNamingFrame(right_panel)
        self.naming_frame.pack(fill="x", pady=(0, 20))
        
        self.btn_process = ctk.CTkButton(right_panel, text="Process Pages", height=44, corner_radius=10,
                                         fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                                         font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=15, weight="bold"), 
                                         command=self.start_processing)
        self.btn_process.pack(fill="x", pady=10)
        
    def _on_action_change(self):
        action = self.action_var.get()
        if action == "split":
            self.lbl_param.configure(text="")
            self.ent_param.grid_remove()
        elif action == "extract":
            self.lbl_param.configure(text="Pages to Extract (e.g. 1, 3, 5-10):")
            self.ent_param.grid()
        elif action == "remove":
            self.lbl_param.configure(text="Pages to Remove (e.g. 2, 4):")
            self.ent_param.grid()
        elif action == "rotate":
            self.lbl_param.configure(text="Pages to Rotate +90deg (e.g. 1, 4):")
            self.ent_param.grid()
            
    def on_files_dropped(self, files):
        pdf_files = [f for f in files if f.lower().endswith('.pdf')]
        if len(pdf_files) < len(files):
            self.app.show_toast("Warning", "Only PDFs are allowed here.")
            
        current = self.file_list.get_files()
        if len(current) + len(pdf_files) > 1:
            self.app.show_toast("Warning", "Only 1 PDF can be managed at a time.")
            pdf_files = pdf_files[:1]
            self.file_list.clear_files()
            
        self.file_list.add_files(pdf_files)
        
    def start_processing(self):
        files = self.file_list.get_files()
        if not files:
            self.app.show_toast("Error", "Please add 1 PDF file.", is_error=True)
            return

        if not self.app.check_operation_allowed():
            return
            
        action = self.action_var.get()
        param_text = self.ent_param.get().strip() if self.ent_param.winfo_ismapped() else ""
        
        if action in ["extract", "remove", "rotate"] and not param_text:
            self.app.show_toast("Error", "Please provide page numbers.", is_error=True)
            return
            
        naming_data = self.naming_frame.get_data()
        try:
            out_path = FileManager.generate_simple_output_path(
                output_dir=naming_data.get("output_dir", ""),
                output_filename=naming_data.get("output_filename", "")
            )
        except ValueError as e:
            self.app.show_toast("Error", str(e), is_error=True)
            return
            
        self.btn_process.configure(state="disabled", text="Processing...")
        threading.Thread(target=self._process_thread, args=(files[0], out_path, action, param_text), daemon=True).start()
        
    def _process_thread(self, pdf_path, out_path, action, param_text):
        try:
            from pypdf import PdfReader, PdfWriter
            import os
            
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)
            
            # Helper to parse page strings
            def parse_pages(text, mx):
                pages = set()
                parts = text.replace(" ", "").split(",")
                for p in parts:
                    if "-" in p:
                        s, e = map(int, p.split("-"))
                        pages.update(range(s, e + 1))
                    elif p.isdigit():
                        pages.add(int(p))
                return [p for p in sorted(list(pages)) if 1 <= p <= mx]
                
            writer = PdfWriter()
            
            if action == "split":
                import os
                out_dir = os.path.dirname(out_path)
                base_name = os.path.splitext(os.path.basename(out_path))[0]
                for i, page in enumerate(reader.pages):
                    w = PdfWriter()
                    w.add_page(page)
                    p = os.path.join(out_dir, f"{base_name}_page_{i+1}.pdf")
                    with open(p, "wb") as f:
                        w.write(f)
                msg = f"Split {total_pages} pages successfully."
                
            else:
                target_pages = parse_pages(param_text, total_pages)
                if not target_pages:
                    raise Exception("No valid pages specified within document bounds.")
                    
                if action == "extract":
                    for pg in target_pages:
                        writer.add_page(reader.pages[pg - 1])
                    msg = f"Extracted {len(target_pages)} pages successfully."
                    
                elif action == "remove":
                    for i, page in enumerate(reader.pages):
                        if (i + 1) not in target_pages:
                            writer.add_page(page)
                    msg = f"Removed {len(target_pages)} pages. New PDF has {len(writer.pages)} pages."
                    
                elif action == "rotate":
                    for i, page in enumerate(reader.pages):
                        if (i + 1) in target_pages:
                            page.rotate(90)
                        writer.add_page(page)
                    msg = f"Rotated {len(target_pages)} pages successfully."
                    
                with open(out_path, "wb") as f:
                    writer.write(f)

            self.after(0, lambda: self._on_success(msg))
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))
            
    def _on_success(self, msg):
        self.btn_process.configure(state="normal", text="Process PDF")
        self.file_list.clear_files()
        self.app.show_toast("Success", f"{msg}\n\nOperation completed successfully.")
        
    def _on_error(self, err):
        self.btn_process.configure(state="normal", text="Process PDF")
        self.app.show_toast("Failed", str(err), is_error=True)
