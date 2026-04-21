import customtkinter as ctk
from tkinter import Canvas, Entry, Text, END, filedialog, messagebox, font as tkfont
from PIL import Image, ImageTk
import os
from core.pdf_editor_engine import PDFEditorEngine
from core.pdf_editor_state import (
    PDFEditorState, RotateCommand, DeletePageCommand, 
    ReplaceTextCommand, DuplicatePageCommand, AnnotationCommand,
    AddOverlayCommand, UpdateOverlayCommand, DeleteOverlayCommand
)
from .sign_dialogs import SignStampDialog
import datetime
from ui.theme import Theme

class PDFEditorView(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color=Theme.BG_PRIMARY)
        self.app = app_instance
        self.engine = PDFEditorEngine()
        self.state = PDFEditorState()
        
        # Track dragging
        self.is_dragging = False
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self.drag_mode = "move" # or "resize"
        self.mode = "select"
        self.orig_bbox = []
        self.orig_fontsize = 14.0
        
        # Inline text editor state
        self._inline_editor = None       # The Entry/Text widget on canvas
        self._inline_editor_win = None   # Canvas window ID
        self._inline_edit_obj = None     # The PDF text span being edited (None for new text)
        self._inline_edit_mode = None    # "edit" or "add"
        self._inline_edit_pos = None     # (x, y) in PDF coords for new text
        
        self.setup_ui()
        self.update_button_states()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(0, weight=1)

        # 1. Left Panel (Thumbnails)
        self.left_panel = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=Theme.BG_SECONDARY)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 1)) # Thin border feel
        
        # Border separation
        ctk.CTkFrame(self, width=1, fg_color=Theme.BORDER_COLOR).grid(row=0, column=0, sticky="nse")
        
        self.open_btn = ctk.CTkButton(self.left_panel, text="📂 Open PDF", height=36, corner_radius=8,
                                      fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR,
                                      font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                                      command=self.open_pdf)
        self.open_btn.pack(pady=(20, 10), padx=15, fill="x")
        
        self.save_btn = ctk.CTkButton(self.left_panel, text="💾 Save PDF", height=36, corner_radius=8,
                                      fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                                      font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                                      command=self.save_pdf)
        self.save_btn.pack(pady=(0, 20), padx=15, fill="x")
        
        self.thumb_scroll = ctk.CTkScrollableFrame(self.left_panel, label_text="Pages", 
                                                  fg_color="transparent", label_fg_color="transparent",
                                                  label_font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"))
        self.thumb_scroll.pack(expand=True, fill="both", padx=5, pady=5)

        # 2. Center Panel (PDF Canvas & Toolbar)
        self.center_panel = ctk.CTkFrame(self, corner_radius=0, fg_color=Theme.BG_PRIMARY)
        self.center_panel.grid(row=0, column=1, sticky="nsew")
        
        self.toolbar_container = ctk.CTkFrame(self.center_panel, height=60, fg_color=Theme.BG_SECONDARY, corner_radius=0)
        self.toolbar_container.pack(side="top", fill="x")
        
        # Bottom border for toolbar
        ctk.CTkFrame(self.toolbar_container, height=1, fg_color=Theme.BORDER_COLOR).pack(side="bottom", fill="x")
        
        self.toolbar = ctk.CTkScrollableFrame(self.toolbar_container, orientation="horizontal", height=50, fg_color="transparent")
        self.toolbar.pack(fill="both", expand=True, padx=10)
        
        self.create_toolbar_groups()

        self.canvas_frame = ctk.CTkFrame(self.center_panel, fg_color=Theme.BG_PRIMARY, corner_radius=0)
        self.canvas_frame.pack(expand=True, fill="both")
        
        # Vertical scrollbar
        self.v_scrollbar = ctk.CTkScrollbar(self.canvas_frame, orientation="vertical")
        self.v_scrollbar.pack(side="right", fill="y")
        
        # Horizontal scrollbar
        self.h_scrollbar = ctk.CTkScrollbar(self.canvas_frame, orientation="horizontal")
        self.h_scrollbar.pack(side="bottom", fill="x")
        
        self.canvas = Canvas(self.canvas_frame, bg=Theme.BG_PRIMARY, highlightthickness=0, takefocus=True,
                             yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set)
        self.canvas.pack(side="left", expand=True, fill="both")
        
        self.v_scrollbar.configure(command=self.canvas.yview)
        self.h_scrollbar.configure(command=self.canvas.xview)
        
        # Mouse wheel scrolling
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)
        
        # Bindings for Canvas Interaction
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Leave>", lambda e: self.canvas.delete("hover_highlight"))
        
        # OCR Prompt Frame (hidden by default)
        self.ocr_prompt = ctk.CTkFrame(self.canvas_frame, fg_color=Theme.BG_SECONDARY, height=44, 
                                       corner_radius=10, border_width=1, border_color=Theme.ACCENT_BLUE)
        self.ocr_lbl = ctk.CTkLabel(self.ocr_prompt, text="📑 Scanned PDF detected. Text is not selectable.", font=(Theme.FONT_FAMILY, 12))
        self.ocr_lbl.pack(side="left", padx=15)
        self.ocr_btn = ctk.CTkButton(self.ocr_prompt, text="Run OCR to Edit", width=120, height=30, corner_radius=6,
                                     fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                                     font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                                     command=self.run_ocr)
        self.ocr_btn.pack(side="left", padx=(0, 15))
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Button-3>", self.show_context_menu)
        
        # KEY BINDINGS: Bind to root window to catch keys regardless of focus
        self.after(500, self._bind_keys)
        
    def _bind_keys(self):
        try:
            root = self.winfo_toplevel()
            root.bind("<Delete>", lambda e: self.delete_overlay())
            root.bind("<BackSpace>", lambda e: self.delete_overlay())
        except:
            pass

        # Status Bar
        self.status_bar = ctk.CTkFrame(self.center_panel, height=28, corner_radius=0, fg_color=Theme.BG_SECONDARY)
        self.status_bar.pack(side="bottom", fill="x")
        
        # Top border for status bar
        ctk.CTkFrame(self.status_bar, height=1, fg_color=Theme.BORDER_COLOR).place(relx=0, rely=0, relwidth=1)
        
        self.status_lbl = ctk.CTkLabel(self.status_bar, text="Ready", font=(Theme.FONT_FAMILY, 11), text_color=Theme.TEXT_MUTED)
        self.status_lbl.pack(side="left", padx=15)
        self.page_info_lbl = ctk.CTkLabel(self.status_bar, text="Page 0 of 0", font=(Theme.FONT_FAMILY, 11), text_color=Theme.TEXT_MUTED)
        self.page_info_lbl.pack(side="right", padx=15)
        self.zoom_lbl = ctk.CTkLabel(self.status_bar, text="Zoom 100%", font=(Theme.FONT_FAMILY, 11), text_color=Theme.TEXT_MUTED)
        self.zoom_lbl.pack(side="right", padx=15)

        # 3. Right Panel (Properties)
        self.right_panel = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=Theme.BG_SECONDARY)
        self.right_panel.grid(row=0, column=2, sticky="nsew", padx=(1, 0))
        
        # Border separation
        ctk.CTkFrame(self, width=1, fg_color=Theme.BORDER_COLOR).grid(row=0, column=2, sticky="nsw")
        
        ctk.CTkLabel(self.right_panel, text="Properties", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=16, weight="bold")).pack(pady=20)
        self.prop_content = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.prop_content.pack(expand=True, fill="both", padx=15)

    def create_toolbar_groups(self):
        # Group 1: View
        g_view = self.create_group("View")
        self.zoom_in_btn = self.add_tool(g_view, "➕", "Zoom In", self.zoom_in)
        self.zoom_out_btn = self.add_tool(g_view, "➖", "Zoom Out", self.zoom_out)
        
        # Group 2: History
        g_hist = self.create_group("History")
        self.undo_btn = self.add_tool(g_hist, "↩ Undo", "Undo last action", self.undo_action)
        self.redo_btn = self.add_tool(g_hist, "↪ Redo", "Redo last action", self.redo_action)
        
        # Group 3: Page
        g_page = self.create_group("Page")
        self.rot_btn = self.add_tool(g_page, "🔄 Rotate", "Rotate Page 90° CW", self.rotate_current_page)
        self.dup_btn = self.add_tool(g_page, "📋 Duplicate", "Duplicate Page", self.duplicate_current_page)
        self.del_btn = self.add_tool(g_page, "🗑 Delete", "Delete Page", self.delete_current_page, color="#e74c3c")
        
        # Group 4: Annotations
        g_annot = self.create_group("Annotations")
        self.text_tool_btn = self.add_tool(g_annot, "Add Text", "Add Text to Page", lambda: self.set_annot_mode("text"), width=80)
        
        # Note: Sign & Stamp removed (now standalone module)

    def set_select_mode(self):
        self.mode = "select"
        self.set_status("Select mode active")

    def set_annot_mode(self, annot_type):
        self.mode = annot_type
        self.set_status(f"{annot_type.capitalize()} mode active")

    def create_group(self, name):
        frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        frame.pack(side="left", padx=5)
        return frame

    def add_tool(self, parent, text, tooltip, command, width=70, color=None, text_color=None):
        btn = ctk.CTkButton(parent, text=text, width=width, height=32, corner_radius=6,
                            fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR,
                            font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=12),
                            command=command)
        if color: btn.configure(fg_color=color, border_width=0)
        if text_color: btn.configure(text_color=text_color)
        btn.pack(side="left", padx=4, pady=4)
        btn.bind("<Enter>", lambda e: self.set_status(tooltip))
        btn.bind("<Leave>", lambda e: self.set_status("Ready"))
        
        # Track buttons to highlight active tool
        if not hasattr(self, '_tool_btns'): self._tool_btns = []
        self._tool_btns.append((btn, command))
        return btn

    def set_annot_mode(self, mode):
        self.mode = mode
        self.set_status(f"{mode.capitalize()} mode active. Click on page.")
        # Highlight active tool
        for btn, cmd in self._tool_btns:
            if btn == self.text_tool_btn and mode == "text":
                btn.configure(fg_color=Theme.ACCENT_BLUE, border_width=0)
            elif btn == self.high_tool_btn and mode == "highlight":
                btn.configure(fg_color="#3498db")
            else:
                # Reset others to default color? Actually simpler to just use a toggle logic
                pass

    def set_status(self, msg):
        self.status_lbl.configure(text=msg)

    def update_button_states(self):
        doc_open = self.state.doc is not None
        btns = [self.save_btn, self.zoom_in_btn, self.zoom_out_btn, 
                self.rot_btn, self.dup_btn, self.del_btn]
        state = "normal" if doc_open else "disabled"
        for b in btns: b.configure(state=state)
        self.undo_btn.configure(state="normal" if self.state.can_undo() else "disabled")
        self.redo_btn.configure(state="normal" if self.state.can_redo() else "disabled")

    def open_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            if self.app.check_operation_allowed():
                self.state.load_doc(path)
                # CRITICAL SYNC: Ensure engine uses the exact same document object as state
                self.engine.doc = self.state.doc
                self.load_pdf_data()
                self.set_status(f"Opened: {os.path.basename(path)}")

    def load_pdf_data(self):
        try:
            # Check for text layer
            has_text = False
            for i in range(len(self.state.doc)):
                if self.state.doc[i].get_text("words"):
                    has_text = True; break
            
            if not has_text and self.state.current_page_index not in self.engine.ocr_page_data:
                self.ocr_prompt.place(relx=0.5, y=20, anchor="n")
            else:
                self.ocr_prompt.place_forget()
                
            for widget in self.thumb_scroll.winfo_children(): widget.destroy()
            thumbs = self.engine.get_thumbnails()
            for i, thumb_img in enumerate(thumbs):
                thumb_ctk = ctk.CTkImage(light_image=thumb_img, dark_image=thumb_img, size=(120, 160))
                btn = ctk.CTkButton(self.thumb_scroll, image=thumb_ctk, text=f"Page {i+1}", 
                                    compound="top", fg_color="transparent", corner_radius=8,
                                    font=(Theme.FONT_FAMILY, 11),
                                    command=lambda p=i: self.select_page(p))
                btn.pack(pady=5, padx=5)
                if i == self.state.current_page_index: btn.configure(fg_color=Theme.ACCENT_BLUE, border_width=0)
            self.render_page()
            self.update_properties_panel()
            self.update_button_states()
        except Exception as e:
            self.app.show_toast("Error", str(e), is_error=True)

    def select_page(self, page_num):
        self.state.current_page_index = page_num
        # Clear selection when switching pages to keep properties panel in sync
        self.state.selected_object = None
        self.state.selected_overlay = None
        self.load_pdf_data()

    def render_page(self):
        if not self.state.doc: return
        img = self.engine.get_page_image(self.state.current_page_index, zoom=self.state.zoom_level)
        if img:
            self.photo = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(10, 10, anchor="nw", image=self.photo, tags="pdf")
            self.canvas.config(scrollregion=(0, 0, img.width + 20, img.height + 20))
        else:
            self.canvas.delete("all")
            self.canvas.config(scrollregion=(0, 0, 100, 100))

        # Render session overlays (ALWAYS, on top of PDF image)
        self.render_overlays()
        
        # Render selection highlight for PDF objects
        self.render_content_highlights()
        
        if self.state.doc:
            self.page_info_lbl.configure(text=f"Page {self.state.current_page_index+1} of {len(self.state.doc)}")
            self.zoom_lbl.configure(text=f"Zoom {int(self.state.zoom_level*100)}%")

    def render_content_highlights(self):
        """Draws a highlight box around the selected original PDF object."""
        self.canvas.delete("content_highlight")
        if self.state.selected_object:
            bbox = self.state.selected_object["bbox"]
            zoom = self.state.zoom_level
            x0 = bbox[0] * zoom + 10
            y0 = bbox[1] * zoom + 10
            x1 = bbox[2] * zoom + 10
            y1 = bbox[3] * zoom + 10
            # A distinct color/style compared to overlays (dotted blue)
            # Make it more prominent (width=3)
            self.canvas.create_rectangle(x0, y0, x1, y1, outline=Theme.ACCENT_BLUE, width=3, dash=(4, 4), tags="content_highlight")

    def _on_mousewheel(self, event):
        """Scroll canvas vertically with mouse wheel."""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_shift_mousewheel(self, event):
        """Scroll canvas horizontally with Shift + mouse wheel."""
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def render_overlays(self):
        """Draws session-scoped signatures/stamps on the canvas."""
        self.canvas.delete("overlay")
        overlays = self.state.page_overlays.get(self.state.current_page_index, [])
        for i, ov in enumerate(overlays):
            bbox = ov["bbox"]
            x0 = bbox[0] * self.state.zoom_level + 10
            y0 = bbox[1] * self.state.zoom_level + 10
            x1 = bbox[2] * self.state.zoom_level + 10
            y1 = bbox[3] * self.state.zoom_level + 10
            
            # For simplicity, we just draw placeholders if image is not loaded
            tags = ("overlay", f"ov_{i}")
            zoom = self.state.zoom_level
            
            if ov["type"] == "image":
                pil_img = Image.open(ov["path"]).convert("RGBA")
                # Handle rotation (PIL uses CCW, our data uses CW, so -angle)
                if ov.get("rotation"):
                    pil_img = pil_img.rotate(-ov["rotation"], expand=True, resample=Image.Resampling.BICUBIC)
                
                # Handle opacity
                if ov.get("opacity", 1.0) < 1.0:
                    alpha = pil_img.split()[3]
                    alpha = alpha.point(lambda p: p * ov["opacity"])
                    pil_img.putalpha(alpha)
                
                # High-quality resize to fit bbox on canvas
                pil_img = pil_img.resize((int(x1-x0), int(y1-y0)), Image.Resampling.LANCZOS)
                
                if not hasattr(self, 'overlay_images'): self.overlay_images = {}
                photo = ImageTk.PhotoImage(pil_img)
                self.overlay_images[f"ov_{i}"] = photo
                self.canvas.create_image(x0, y0, anchor="nw", image=photo, tags=tags)
                
            elif ov["type"] == "text":
                # AUTO-FIT SCALING: Derive font size directly from current box height
                # This is the most robust way to ensure text and box always match
                box_h_pts = max(5, ov["bbox"][3] - ov["bbox"][1])
                line_count = ov["text"].count("\n") + 1
                if "\n\n\n" in ov["text"]: line_count = 4 # Handle custom stamp signature space
                
                # Professional ratio: fill ~70% of line height
                calc_fontsize = int(box_h_pts / (line_count * 1.35))
                calc_fontsize = max(6, calc_fontsize)
                
                # Check for rotation/opacity (needs Pillow path)
                if ov.get("rotation") or ov.get("opacity", 1.0) < 1.0:
                    from PIL import Image, ImageTk, ImageDraw, ImageFont
                    tw, th = int(x1-x0), int(y1-y0)
                    t_img = Image.new("RGBA", (max(1, tw), max(1, th)), (0,0,0,0))
                    draw = ImageDraw.Draw(t_img)
                    try:
                        font = ImageFont.truetype("arial.ttf", int(calc_fontsize * zoom))
                    except:
                        font = ImageFont.load_default()
                    
                    # Render multi-line centered
                    lines = ov["text"].split("\n")
                    curr_y = 5
                    for line in lines:
                        try:
                            l, t, r, b = draw.textbbox((0,0), line, font=font)
                            draw.text(((tw-(r-l))/2, curr_y), line, fill=ov.get("color", "red"), font=font)
                            curr_y += (b-t) + 5
                        except: pass
                    
                    if ov.get("rotation"): t_img = t_img.rotate(-ov["rotation"], expand=True)
                    if ov.get("opacity", 1.0) < 1.0:
                        alpha = t_img.split()[3].point(lambda p: p * ov["opacity"])
                        t_img.putalpha(alpha)
                        
                    photo = ImageTk.PhotoImage(t_img)
                    if not hasattr(self, 'overlay_images'): self.overlay_images = {}
                    self.overlay_images[f"ov_{i}"] = photo
                    self.canvas.create_image((x0+x1)/2, (y0+y1)/2, anchor="center", image=photo, tags=tags)
                else:
                    # High-performance standard path
                    self.canvas.create_text((x0+x1)/2, (y0+y1)/2, text=ov["text"], 
                                            fill=ov.get("color", "red"), 
                                            font=("Arial", int(calc_fontsize * zoom), 
                                                  "bold" if ov.get("bold", True) else "normal"), 
                                            justify=ov.get("align_str", "center"),
                                            anchor="center",
                                            tags=tags)
            
            # Draw dotted border if selected
            if ov == self.state.selected_overlay:
                self.canvas.create_rectangle(x0-2, y0-2, x1+2, y1+2, 
                                             outline="#3498db", width=2, dash=(4, 4), tags=tags)
                # Draw resize handle
                self.canvas.create_rectangle(x1-5, y1-5, x1+2, y1+2, fill="#3498db", outline="white", tags=tags)
            
            # Invisible hit-box
            self.canvas.create_rectangle(x0, y0, x1, y1, fill="", outline="", tags=(tags, "hitbox"))
            
            # Selection highlight (disappears on save, only for editing)
            if self.state.selected_overlay == ov:
                self.canvas.create_rectangle(x0, y0, x1, y1, outline="#3498db", width=1, dash=(4,2), tags=tags)
                # Resize handle
                self.canvas.create_rectangle(x1-6, y1-6, x1, y1, fill="#3498db", tags=tags)

    def on_canvas_click(self, event):
        self.canvas.focus_set() # Ensure canvas has focus for Delete key
        x = (self.canvas.canvasx(event.x) - 10) / self.state.zoom_level
        y = (self.canvas.canvasy(event.y) - 10) / self.state.zoom_level
        
        # Check overlays first
        self.state.selected_overlay = None
        overlays = self.state.page_overlays.get(self.state.current_page_index, [])
        for ov in reversed(overlays):
            b = ov["bbox"]
            if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
                self.state.selected_overlay = ov
                self.is_dragging = True
                self.last_mouse_x = x
                self.last_mouse_y = y
                # Corner detection for resize
                if x > b[2] - 10 and y > b[3] - 10:
                    self.drag_mode = "resize"
                else:
                    self.drag_mode = "move"
                self.orig_bbox = list(ov["bbox"])
                self.orig_fontsize = ov.get("fontsize", 14)
                
                # Selection Priority: If click is on an overlay, stop here
                self.render_overlays()
                self.show_overlay_properties(ov)
                return
        
        # 2. Check for PDF blocks (Text/Images)
        self.state.selected_object = None
        objs = self.engine.get_page_objects(self.state.current_page_index)
        for obj in objs:
            b = obj["bbox"]
            # Add 5-pixel padding for much easier text selection ("selective")
            if b[0]-5 <= x <= b[2]+5 and b[1]-5 <= y <= b[3]+5:
                if self.mode == "highlight":
                    if obj.get("type") == "text":
                        self.apply_highlight(obj)
                    return
                else: # Select mode
                    self.state.selected_object = obj
                    self.show_pdf_object_properties(obj)
                    self.render_page() # Highlight selected PDF block
                    return
        
        self.state.selected_object = None
        self.clear_properties()
        
        self.render_overlays()
        if self.state.selected_overlay:
            self.show_overlay_properties(self.state.selected_overlay)
        else:
            self.clear_properties()

    def on_canvas_drag(self, event):
        if not self.is_dragging or not self.state.selected_overlay: return
        
        x = (self.canvas.canvasx(event.x) - 10) / self.state.zoom_level
        y = (self.canvas.canvasy(event.y) - 10) / self.state.zoom_level
        dx = x - self.last_mouse_x
        dy = y - self.last_mouse_y
        
        ov = self.state.selected_overlay
        if self.drag_mode == "move":
            ov["bbox"] = [ov["bbox"][0]+dx, ov["bbox"][1]+dy, ov["bbox"][2]+dx, ov["bbox"][3]+dy]
        else:
            # Absolute Resize: Move the corner directly to mouse position.
            # The new image-based rendering in render_overlays handles the scaling perfectly.
            ov["bbox"][2] = max(ov["bbox"][0] + 10, x)
            ov["bbox"][3] = max(ov["bbox"][1] + 10, y)
            
        self.last_mouse_x = x
        self.last_mouse_y = y
        self.render_overlays()
        # skip update_properties_panel here to avoid lag during drag

    def on_canvas_release(self, event):
        if self.is_dragging:
            self.update_properties_panel()
        self.is_dragging = False

    def on_canvas_motion(self, event):
        if not self.state.doc: return
        x = (self.canvas.canvasx(event.x) - 10) / self.state.zoom_level
        y = (self.canvas.canvasy(event.y) - 10) / self.state.zoom_level
        zoom = self.state.zoom_level
        
        objs = self.engine.get_page_objects(self.state.current_page_index)
        for obj in objs:
            b = obj["bbox"]
            if b[0]-2 <= x <= b[2]+2 and b[1]-2 <= y <= b[3]+2:
                self.canvas.delete("hover_highlight")
                self.canvas.create_rectangle(
                    b[0]*zoom+10, b[1]*zoom+10, b[2]*zoom+10, b[3]*zoom+10,
                    outline="#bdc3c7", width=1, dash=(2, 2), tags="hover_highlight"
                )
                return
        self.canvas.delete("hover_highlight")

    def run_ocr(self):
        self.ocr_btn.configure(state="disabled", text="Scanning...")
        self.app.show_toast("OCR", "Scanning page for text... Please wait.")
        
        def do_ocr():
            if self.engine.run_ocr_on_page(self.state.current_page_index):
                self.after(0, self.on_ocr_success)
            else:
                self.after(0, lambda: self.app.show_toast("Error", "OCR failed.", is_error=True))
                self.after(0, lambda: self.ocr_btn.configure(state="normal", text="Run OCR to Edit"))
        
        import threading
        threading.Thread(target=do_ocr, daemon=True).start()

    def on_ocr_success(self):
        self.ocr_prompt.place_forget()
        self.app.show_toast("Success", "Text is now selectable!")
        self.load_pdf_data()

    def on_canvas_click(self, event):
        self.canvas.focus_set()
        
        # If inline editor is active and click is outside it, commit the edit
        if self._inline_editor is not None:
            self._commit_inline_edit()
            return
        
        x = (self.canvas.canvasx(event.x) - 10) / self.state.zoom_level
        y = (self.canvas.canvasy(event.y) - 10) / self.state.zoom_level
        zoom = self.state.zoom_level
        
        # 1. Handle 'Add Text' mode — open inline editor at click position
        if self.mode == "text":
            self._open_inline_editor_for_new_text(x, y)
            return
            
        # 2. Check overlays first (for selection/drag)
        self.state.selected_overlay = None
        overlays = self.state.page_overlays.get(self.state.current_page_index, [])
        for ov in reversed(overlays):
            b = ov["bbox"]
            if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
                self.state.selected_overlay = ov
                self.is_dragging = True
                self.last_mouse_x = x
                self.last_mouse_y = y
                if x > b[2] - 10 and y > b[3] - 10:
                    self.drag_mode = "resize"
                else:
                    self.drag_mode = "move"
                self.render_page()
                self.update_properties_panel()
                return

        # 3. Check for PDF blocks (text/images)
        objs = self.engine.get_page_objects(self.state.current_page_index)
        selected_obj = None
        
        for obj in reversed(objs):
            b = obj["bbox"]
            if b[0]-5 <= x <= b[2]+5 and b[1]-5 <= y <= b[3]+5:
                if self.mode == "highlight":
                    if obj.get("type") == "text":
                        self.apply_highlight(obj)
                    return
                selected_obj = obj
                break
        
        self.state.selected_object = selected_obj
        
        # 4. If a text span is clicked, open inline editor on it
        if selected_obj and selected_obj.get("type") == "text":
            self.render_page()             # Render first (shows selection highlight)
            self.update_properties_panel()
            self._open_inline_editor_for_existing_text(selected_obj)  # Then open editor ON TOP
            return
        
        if not selected_obj:
            img = self.engine.get_page_image(self.state.current_page_index, zoom=zoom)
            if img:
                pw, ph = img.width / zoom, img.height / zoom
                if 0 <= x <= pw and 0 <= y <= ph:
                    pass
        
        self.render_page()
        self.update_properties_panel()

    # ─── INLINE TEXT EDITOR ON CANVAS ────────────────────────────────────

    def _open_inline_editor_for_existing_text(self, obj):
        """Opens an inline Entry widget directly over the selected text span on the canvas."""
        self._close_inline_editor()  # Close any existing editor first
        
        bbox = obj["bbox"]
        zoom = self.state.zoom_level
        
        # Canvas coordinates
        cx0 = bbox[0] * zoom + 10
        cy0 = bbox[1] * zoom + 10
        cx1 = bbox[2] * zoom + 10
        cy1 = bbox[3] * zoom + 10
        
        width = max(int(cx1 - cx0), 80)
        height = max(int(cy1 - cy0), 22)
        
        # Determine font for the editor widget
        font_name_orig = obj.get("font", "Arial")
        font_size = max(8, int(obj.get("size", 12) * zoom * 0.75))  # Scale for screen display
        flags = obj.get("flags", 0)
        heavier_terms = ["bold", "heavy", "black", "semibold", "medium", "demi"]
        is_bold = (flags & 16) or any(t in font_name_orig.lower() for t in heavier_terms)
        is_italic = (flags & 2) or "italic" in font_name_orig.lower()
        
        # Map font name for Tkinter display
        display_font_name = self._map_font_for_display(font_name_orig)
        font_weight = "bold" if is_bold else "normal"
        font_slant = "italic" if is_italic else "roman"
        editor_font = tkfont.Font(family=display_font_name, size=font_size, 
                                   weight=font_weight, slant=font_slant)
        
        # Get text color for the editor
        color_val = obj.get("color", 0)
        if isinstance(color_val, int):
            fg_color = f"#{color_val:06X}"
        elif isinstance(color_val, str):
            fg_color = color_val
        else:
            fg_color = "#000000"
        
        # Create Entry widget
        text_content = obj.get("text", "")
        if "\n" in text_content:
            # Multi-line: use Text widget
            editor = Text(self.canvas, font=editor_font, fg=fg_color, bg="#FFFFEE",
                         insertbackground=fg_color, relief="solid", bd=1,
                         wrap="word", highlightthickness=2, highlightcolor="#3498db")
            editor.insert("1.0", text_content)
            editor.config(width=max(10, width // font_size), height=max(2, text_content.count("\n") + 1))
        else:
            # Single-line: use Entry widget
            editor = Entry(self.canvas, font=editor_font, fg=fg_color, bg="#FFFFEE",
                          insertbackground=fg_color, relief="solid", bd=1,
                          highlightthickness=2, highlightcolor="#3498db")
            editor.insert(0, text_content)
            editor.config(width=max(5, len(text_content) + 3))
        
        # Key bindings
        editor.bind("<Return>", lambda e: self._commit_inline_edit())
        editor.bind("<Escape>", lambda e: self._cancel_inline_edit())
        
        # Place on canvas
        win_id = self.canvas.create_window(cx0, cy0, anchor="nw", window=editor,
                                            width=width, height=height,
                                            tags="inline_editor")
        
        self._inline_editor = editor
        self._inline_editor_win = win_id
        self._inline_edit_obj = obj
        self._inline_edit_mode = "edit"
        
        # Focus and select all text
        editor.focus_set()
        if isinstance(editor, Entry):
            editor.select_range(0, END)
        else:
            editor.tag_add("sel", "1.0", END)

    def _open_inline_editor_for_new_text(self, x, y):
        """Opens an inline Entry widget at the click position for adding new text."""
        self._close_inline_editor()  # Close any existing editor
        
        zoom = self.state.zoom_level
        cx = x * zoom + 10
        cy = y * zoom + 10
        
        font_size = max(8, int(14 * zoom * 0.75))
        editor_font = tkfont.Font(family="Arial", size=font_size)
        
        editor = Entry(self.canvas, font=editor_font, fg="#000000", bg="#FFFFEE",
                      insertbackground="#000000", relief="solid", bd=1,
                      highlightthickness=2, highlightcolor="#3498db")
        editor.config(width=25)
        
        editor.bind("<Return>", lambda e: self._commit_inline_edit())
        editor.bind("<Escape>", lambda e: self._cancel_inline_edit())
        
        width = max(200, int(200 * zoom))
        height = max(24, int(28 * zoom))
        
        win_id = self.canvas.create_window(cx, cy, anchor="nw", window=editor,
                                            width=width, height=height,
                                            tags="inline_editor")
        
        self._inline_editor = editor
        self._inline_editor_win = win_id
        self._inline_edit_obj = None
        self._inline_edit_mode = "add"
        self._inline_edit_pos = (x, y)
        
        editor.focus_set()

    def _commit_inline_edit(self):
        """Commits the inline editor content — either updates existing text or creates new overlay."""
        if self._inline_editor is None:
            return
        
        # Get the text from editor
        if isinstance(self._inline_editor, Text):
            new_text = self._inline_editor.get("1.0", "end-1c")
        else:
            new_text = self._inline_editor.get()
        
        new_text = new_text.strip()
        
        if self._inline_edit_mode == "edit" and self._inline_edit_obj is not None:
            # Editing existing PDF text — apply with format preservation
            obj = self._inline_edit_obj
            if new_text and new_text != obj.get("text", ""):
                # Detect formatting from original span
                flags = obj.get("flags", 0)
                heavier_terms = ["bold", "heavy", "black", "semibold", "medium", "demi"]
                is_bold = (flags & 16) or any(t in obj.get("font", "").lower() for t in heavier_terms)
                is_underlined = obj.get("is_underlined", False)
                
                self.apply_text_change(obj, new_text,
                                       force_bold=is_bold,
                                       force_underline=is_underlined)
            
        elif self._inline_edit_mode == "add" and new_text:
            # Adding new text — create overlay at click position
            x, y = self._inline_edit_pos
            ov = {
                "type": "text",
                "bbox": [x, y, x + max(150, len(new_text) * 8), y + 30],
                "text": new_text,
                "color": "#000000",
                "fontsize": 14,
                "bold": False,
                "align": 0,
                "rotation": 0,
                "opacity": 1.0
            }
            cmd = AddOverlayCommand(self.state, self.state.current_page_index, ov)
            self.state.push_command(cmd)
            self.state.selected_overlay = ov
            self.mode = "select"  # Switch back to select
        
        self._close_inline_editor()
        self.render_page()
        self.update_properties_panel()

    def _cancel_inline_edit(self):
        """Cancels the inline edit without applying changes."""
        if self._inline_edit_mode == "add":
            self.mode = "select"  # Switch back to select
        self._close_inline_editor()
        self.set_status("Edit cancelled")

    def _close_inline_editor(self):
        """Removes the inline editor widget from the canvas."""
        if self._inline_editor is not None:
            try:
                self._inline_editor.destroy()
            except Exception:
                pass
            self._inline_editor = None
        if self._inline_editor_win is not None:
            try:
                self.canvas.delete(self._inline_editor_win)
            except Exception:
                pass
            self._inline_editor_win = None
        self.canvas.delete("inline_editor")
        self._inline_edit_obj = None
        self._inline_edit_mode = None
        self._inline_edit_pos = None

    def _map_font_for_display(self, pdf_font_name):
        """Maps a PDF font name to a Tkinter-compatible font family for inline editing."""
        name = pdf_font_name.lower()
        # Remove subset prefix (e.g., "ABCDEF+")
        if "+" in name:
            name = name.split("+", 1)[1]
        # Remove style suffixes
        for suffix in ["-bold", "-italic", "-bolditalic", "-regular", ",bold", ",italic", "-roman"]:
            name = name.replace(suffix, "")
        name = name.replace("-", " ").strip()
        
        FONT_MAP = {
            "arial": "Arial", "calibri": "Calibri", "times": "Times New Roman",
            "timesnewroman": "Times New Roman", "cambria": "Cambria",
            "georgia": "Georgia", "verdana": "Verdana", "tahoma": "Tahoma",
            "segoeui": "Segoe UI", "consolas": "Consolas", "couriernew": "Courier New",
            "courier": "Courier New", "roboto": "Segoe UI", "helvetica": "Arial",
            "helv": "Arial", "tiro": "Times New Roman", "cour": "Courier New",
        }
        clean = name.replace(" ", "").lower()
        for key, val in FONT_MAP.items():
            if key in clean or clean in key:
                return val
        return "Arial"  # Safe fallback

    def add_new_text_overlay(self, x, y):
        """Creates a text overlay (used by non-inline paths)."""
        ov = {
            "type": "text",
            "bbox": [x, y, x + 150, y + 30],
            "text": "New Text ...",
            "color": "#000000",
            "fontsize": 14,
            "bold": False,
            "align": 0,
            "rotation": 0,
            "opacity": 1.0
        }
        cmd = AddOverlayCommand(self.state, self.state.current_page_index, ov)
        self.state.push_command(cmd)
        self.state.selected_overlay = ov
        self.render_page()
        self.update_properties_panel()

    def open_sign_stamp_module(self):
        SignStampDialog(self.master, on_apply=self.handle_sign_stamp_apply)

    def handle_sign_stamp_apply(self, data):
        # Offset slightly for each new insertion to avoid overlap confusion
        if not hasattr(self, '_insertion_offset'): self._insertion_offset = 0
        self._insertion_offset = (self._insertion_offset + 30) % 300
        
        x0, y0 = 100 + self._insertion_offset, 100 + self._insertion_offset
        w, h = data.get("width", 150), data.get("height", 50)
        if data["type"] == "text": h = data.get("height", 80) # Adjust for multi-line
        
        ov = {
            "type": data["type"],
            "bbox": [x0, y0, x0 + w, y0 + h],
            "rotation": 0,
            "opacity": 1.0
        }
        
        if data["type"] == "image":
            ov["path"] = data["path"]
        else:
            ov.update({
                "text": data["text"],
                "color": data["color"],
                "fontsize": data["fontsize"],
                "bold": data.get("bold", False),
                "align": data.get("align", 1),
                "align_str": data.get("align_str", "center")
            })
            
        cmd = AddOverlayCommand(self.state, self.state.current_page_index, ov)
        self.state.push_command(cmd)
        self.state.selected_overlay = ov # Auto-select for immediate resize/move
        self.render_page()
        self.update_properties_panel()
        self.canvas.update() 

    def show_overlay_properties(self, ov):
        try:
            for widget in self.prop_content.winfo_children(): widget.destroy()
            ctk.CTkLabel(self.prop_content, text="✒️ Object Properties", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=14, weight="bold")).pack(pady=10)
            
            # Info Frame
            f = ctk.CTkFrame(self.prop_content, fg_color=Theme.BG_PRIMARY, corner_radius=Theme.CORNER_RADIUS, border_width=1, border_color=Theme.BORDER_COLOR)
            f.pack(fill="x", padx=5, pady=5)
            otype = ov["type"].capitalize()
            ctk.CTkLabel(f, text=f"Type: {otype}", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=11, weight="bold")).pack(anchor="w", padx=10, pady=(5, 2))
            ctk.CTkLabel(f, text=f"Page: {self.state.current_page_index + 1}", font=(Theme.FONT_FAMILY, 10), text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=10)
            
            bbox = ov["bbox"]
            pos_text = f"X: {int(bbox[0])} Y: {int(bbox[1])} | W: {int(bbox[2]-bbox[0])} H: {int(bbox[3]-bbox[1])}"
            ctk.CTkLabel(f, text=pos_text, font=(Theme.FONT_FAMILY, 10), text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=10, pady=(0, 5))

            # Controls
            ctk.CTkLabel(self.prop_content, text="Rotation", font=(Theme.FONT_FAMILY, 12)).pack(pady=(12,0))
            rot_slider = ctk.CTkSlider(self.prop_content, from_=0, to=360, button_color=Theme.ACCENT_BLUE, button_hover_color=Theme.ACCENT_HOVER, command=self.update_ov_rotation)
            rot_slider.set(ov.get("rotation", 0)); rot_slider.pack(pady=5)
            
            ctk.CTkLabel(self.prop_content, text="Opacity", font=(Theme.FONT_FAMILY, 12)).pack(pady=(12,0))
            op_slider = ctk.CTkSlider(self.prop_content, from_=0.1, to=1.0, button_color=Theme.ACCENT_BLUE, button_hover_color=Theme.ACCENT_HOVER, command=self.update_ov_opacity)
            op_slider.set(ov.get("opacity", 1.0)); op_slider.pack(pady=5)

            if ov["type"] == "text":
                ctk.CTkLabel(self.prop_content, text="Edit Text", font=(Theme.FONT_FAMILY, 12)).pack(pady=(12,0))
                txt_edit = ctk.CTkTextbox(self.prop_content, height=60, font=(Theme.FONT_FAMILY, 12), border_width=1, border_color=Theme.BORDER_COLOR)
                txt_edit.insert("1.0", ov["text"]); txt_edit.pack(fill="x", pady=5, padx=5)
                ctk.CTkButton(self.prop_content, text="Update Text", height=32, corner_radius=6, 
                              fg_color="transparent", border_width=1, border_color=Theme.ACCENT_BLUE,
                              font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                              command=lambda: self.update_ov_text(txt_edit.get("1.0", "end-1c"))).pack(pady=5, fill="x")

                # Manual Resize Sliders for Stamp
                ctk.CTkLabel(self.prop_content, text="Stamp Width", font=(Theme.FONT_FAMILY, 12)).pack(pady=(12,0))
                w_slider = ctk.CTkSlider(self.prop_content, from_=50, to=800, button_color=Theme.ACCENT_BLUE, command=self.update_ov_width)
                w_slider.set(ov["bbox"][2] - ov["bbox"][0]); w_slider.pack(pady=2)
                
                ctk.CTkLabel(self.prop_content, text="Stamp Height", font=(Theme.FONT_FAMILY, 12)).pack(pady=(10,0))
                h_slider = ctk.CTkSlider(self.prop_content, from_=20, to=500, button_color=Theme.ACCENT_BLUE, command=self.update_ov_height)
                h_slider.set(ov["bbox"][3] - ov["bbox"][1]); h_slider.pack(pady=2)

                # Style Toggles
                style_frame = ctk.CTkFrame(self.prop_content, fg_color="transparent")
                style_frame.pack(fill="x", pady=10)
                
                bold_color = Theme.ACCENT_BLUE if ov.get("bold", True) else "transparent"
                bold_border = 0 if ov.get("bold", True) else 1
                ctk.CTkButton(style_frame, text="BOLD", width=80, height=32, corner_radius=6,
                              fg_color=bold_color, border_width=bold_border, border_color=Theme.BORDER_COLOR,
                              font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                              command=self.update_ov_bold).pack(side="left", padx=5)

                # Color Grid
                color_f = ctk.CTkFrame(self.prop_content, fg_color="transparent")
                color_f.pack(pady=5)
                colors = ["#000000", "#FF0000", "#0000FF", "#008000", "#FFD700", "#FF8C00"] # Slightly better gold
                for c in colors:
                    btn = ctk.CTkButton(color_f, text="", width=24, height=24, corner_radius=12, fg_color=c, hover_color=c, 
                                        command=lambda col=c: self.update_ov_color(col))
                    btn.pack(side="left", padx=2)

            # Layering and General Actions
            layer_f = ctk.CTkFrame(self.prop_content, fg_color="transparent")
            layer_f.pack(fill="x", pady=(15, 5))
            ctk.CTkButton(layer_f, text="⬆ Forward", width=95, height=32, corner_radius=6, fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR, command=self.bring_overlay_forward).pack(side="left", padx=2)
            ctk.CTkButton(layer_f, text="⬇ Backward", width=95, height=32, corner_radius=6, fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR, command=self.send_overlay_backward).pack(side="left", padx=2)
            
            action_f = ctk.CTkFrame(self.prop_content, fg_color="transparent")
            action_f.pack(fill="x", pady=5)
            ctk.CTkButton(action_f, text="📋 Duplicate", width=95, height=32, corner_radius=6, fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR, command=self.duplicate_overlay).pack(side="left", padx=2)
            ctk.CTkButton(action_f, text="🗑 Delete", width=95, height=32, corner_radius=6, fg_color="#e74c3c", hover_color="#c0392b", command=self.delete_overlay).pack(side="left", padx=2)
            
            ctk.CTkButton(self.prop_content, text="Deselect", height=32, corner_radius=6, fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR, text_color=Theme.TEXT_MUTED, command=self.clear_properties).pack(pady=20, fill="x", padx=5)
            
        except Exception as e:
            self.app.show_toast("Error", f"Failed to show overlay props: {str(e)}", is_error=True)

    def update_ov_scale(self, val):
        if self.state.selected_overlay:
            ov = self.state.selected_overlay
            w = 150 * float(val)
            # Maintain aspect ratio for current h/w if possible, or just scale w
            # For now, just scale width and adjust height prop
            h = (ov["bbox"][3] - ov["bbox"][1]) * (w / (ov["bbox"][2]-ov["bbox"][0]))
            ov["bbox"] = [ov["bbox"][0], ov["bbox"][1], ov["bbox"][0]+w, ov["bbox"][1]+h]
            self.render_overlays()
            self.show_overlay_properties(ov)

    def update_ov_text(self, new_text):
        if self.state.selected_overlay:
            self.state.selected_overlay["text"] = new_text
            self.render_overlays()

    def update_ov_fontsize(self, val):
        if self.state.selected_overlay:
            self.state.selected_overlay["fontsize"] = int(float(val))
            self.render_overlays()

    def update_ov_bold(self):
        if self.state.selected_overlay:
            self.state.selected_overlay["bold"] = not self.state.selected_overlay.get("bold", False)
            self.render_overlays()
            self.update_properties_panel()

    def update_ov_color(self, color):
        if self.state.selected_overlay:
            self.state.selected_overlay["color"] = color
            self.render_overlays()
            self.update_properties_panel()


    def update_properties_panel(self):
        """Dispatches properties update based on the current selection state."""
        try:
            # Clear previous content
            for widget in self.prop_content.winfo_children(): widget.destroy()
            
            # Case 1: Overlay selected (Signature/Stamp)
            if self.state.selected_overlay:
                self.show_overlay_properties(self.state.selected_overlay)
            # Case 2: PDF Content object selected (Text/Image)
            elif self.state.selected_object:
                self.show_pdf_object_properties(self.state.selected_object)
            # Case 3: Page selected (default when a document is open)
            elif self.state.doc:
                self.show_page_properties()
            # Case 4: Nothing
            else:
                self.show_no_selection_properties()
                
            self.prop_content.update()
        except Exception as e:
            self.app.show_toast("Error", f"Failed to refresh properties: {str(e)}", is_error=True)

    def show_no_selection_properties(self):
        ctk.CTkLabel(self.prop_content, text="Properties", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=14, weight="bold")).pack(pady=10)
        ctk.CTkLabel(self.prop_content, text="No object selected", font=(Theme.FONT_FAMILY, 11), text_color=Theme.TEXT_MUTED).pack(pady=20)

    def show_page_properties(self):
        ctk.CTkLabel(self.prop_content, text="📄 Page Properties", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=14, weight="bold")).pack(pady=10)
        
        page_num = self.state.current_page_index
        page = self.state.doc[page_num]
        rect = page.rect
        
        f = ctk.CTkFrame(self.prop_content, fg_color=Theme.BG_PRIMARY, corner_radius=Theme.CORNER_RADIUS, border_width=1, border_color=Theme.BORDER_COLOR)
        f.pack(fill="x", padx=5, pady=5)
        
        ctk.CTkLabel(f, text=f"Current Page: {page_num + 1}", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=11, weight="bold")).pack(anchor="w", padx=10, pady=(10, 2))
        ctk.CTkLabel(f, text=f"Total Pages: {len(self.state.doc)}", font=(Theme.FONT_FAMILY, 11), text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=10)
        ctk.CTkLabel(f, text=f"Dimensions: {int(rect.width)} x {int(rect.height)} pt", font=(Theme.FONT_FAMILY, 10), text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=10)
        ctk.CTkLabel(f, text=f"Rotation: {page.rotation}°", font=(Theme.FONT_FAMILY, 10), text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=10)
        ctk.CTkLabel(f, text=f"Zoom Level: {int(self.state.zoom_level * 100)}%", font=(Theme.FONT_FAMILY, 10), text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=10, pady=(0, 10))

    def show_pdf_object_properties(self, obj, event=None):
        try:
            lbl_title = ctk.CTkLabel(self.prop_content, text="📄 Content Properties", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=14, weight="bold"))
            lbl_title.pack(pady=(10, 15))
            
            # 1. Info Frame
            info_frame = ctk.CTkFrame(self.prop_content, fg_color=Theme.BG_PRIMARY, corner_radius=Theme.CORNER_RADIUS, border_width=1, border_color=Theme.BORDER_COLOR)
            info_frame.pack(fill="x", pady=(0, 15), padx=5)
            
            otype = obj.get("type", "unknown").capitalize()
            if obj.get("synthetic"): otype += " (OCR)"
            
            bbox = obj.get("bbox", [0,0,0,0])
            ctk.CTkLabel(info_frame, text=f"Type: {otype}", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=11, weight="bold")).pack(anchor="w", padx=10, pady=(10, 2))
            
            pos_text = f"X: {int(bbox[0])} | Y: {int(bbox[1])} | W: {int(bbox[2]-bbox[0])} | H: {int(bbox[3]-bbox[1])}"
            ctk.CTkLabel(info_frame, text=pos_text, font=(Theme.FONT_FAMILY, 10), text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=10)
            
            if obj.get("type") == "text":
                font_name = obj.get("font", "Unknown")
                font_size = int(float(obj.get("size", 12)))
                color_val = obj.get("color", 0)
                
                # Format color as hex for display
                if isinstance(color_val, int):
                    color_hex = f"#{color_val:06X}"
                elif isinstance(color_val, str):
                    color_hex = color_val
                else:
                    color_hex = str(color_val)
                
                # Detect styles
                flags = obj.get("flags", 0)
                heavier_terms = ["bold", "heavy", "black", "semibold", "medium", "demi"]
                is_bold = (flags & 16) or any(t in font_name.lower() for t in heavier_terms)
                is_italic = (flags & 2) or "italic" in font_name.lower() or "oblique" in font_name.lower()
                is_underlined = obj.get("is_underlined", False)
                
                style_parts = []
                if is_bold: style_parts.append("Bold")
                if is_italic: style_parts.append("Italic")
                if is_underlined: style_parts.append("Underline")
                style_str = " + ".join(style_parts) if style_parts else "Standard"
                
                ctk.CTkLabel(info_frame, text=f"Font: {font_name}", font=(Theme.FONT_FAMILY, 10), text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=10)
                ctk.CTkLabel(info_frame, text=f"Size: {font_size} pt | Style: {style_str}", font=(Theme.FONT_FAMILY, 10), text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=10)
                ctk.CTkLabel(info_frame, text=f"Color: {color_hex}", font=(Theme.FONT_FAMILY, 10), text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=10, pady=(0, 10))
                
                # Style overrides
                self.force_bold_var = ctk.BooleanVar(value=is_bold)
                self.bold_chk = ctk.CTkCheckBox(self.prop_content, text="Bold Style", variable=self.force_bold_var, font=(Theme.FONT_FAMILY, 12), border_color=Theme.BORDER_COLOR, hover_color=Theme.ACCENT_BLUE)
                self.bold_chk.pack(anchor="w", padx=10, pady=2)
                
                self.force_under_var = ctk.BooleanVar(value=is_underlined)
                self.under_chk = ctk.CTkCheckBox(self.prop_content, text="Underline Style", variable=self.force_under_var, font=(Theme.FONT_FAMILY, 12), border_color=Theme.BORDER_COLOR, hover_color=Theme.ACCENT_BLUE)
                self.under_chk.pack(anchor="w", padx=10, pady=2)
                
                # Edit Area
                ctk.CTkLabel(self.prop_content, text="Edit Text Content:", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=12, weight="bold")).pack(anchor="w", padx=10, pady=(15, 5))
                self.active_txt_box = ctk.CTkTextbox(self.prop_content, height=120, font=(Theme.FONT_FAMILY, 12), border_width=1, border_color=Theme.BORDER_COLOR)
                self.active_txt_box.pack(fill="x", padx=10, pady=5)
                self.active_txt_box.insert("1.0", obj.get("text", ""))
                
                btn_apply = ctk.CTkButton(self.prop_content, text="✅ Apply Changes", 
                                          height=40, corner_radius=10,
                                          font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=13, weight="bold"),
                                          fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                                          command=lambda: self.apply_text_change(obj, 
                                                                               self.active_txt_box.get("1.0", "end-1c"),
                                                                               force_bold=self.force_bold_var.get(),
                                                                               force_underline=self.force_under_var.get()))
                btn_apply.pack(fill="x", padx=10, pady=10)
                
                btn_highlight = ctk.CTkButton(self.prop_content, text="🖌 Highlight Selection", 
                                             height=32, corner_radius=8,
                                             fg_color="transparent", border_width=1, border_color="#f1c40f",
                                             text_color="#f1c40f", hover_color="#34495e",
                                             font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                                             command=lambda: self.apply_highlight(obj))
                btn_highlight.pack(fill="x", padx=10, pady=2)
            
            # Action: Deselect
            ctk.CTkButton(self.prop_content, text="Deselect", height=32, corner_radius=6, fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR, text_color=Theme.TEXT_MUTED, command=self.clear_properties).pack(pady=20, fill="x", padx=10)

        except Exception as e:
            self.app.show_toast("Error", f"Failed to show properties: {str(e)}", is_error=True)

    # show_overlay_properties is now consolidated above

    def apply_highlight(self, obj):
        """Applies a highlight annotation specifically to the selected portion of text if available."""
        page = self.state.doc[self.state.current_page_index]
        
        # 1. Determine the text to highlight
        highlight_text = ""
        try:
            # Try to get selection from the active textbox in properties panel
            if hasattr(self, 'active_txt_box'):
                highlight_text = self.active_txt_box.selection_get()
        except:
            pass # No selection
            
        # 2. Extract rectangles for the highlight
        import fitz
        hit_rects = []
        
        if highlight_text:
            # Substring highlight mode
            # 1. Sanitize: Remove newlines and collapse spaces for search_for
            search_query = " ".join(highlight_text.split())
            
            clip_rect = fitz.Rect(obj["bbox"]).irect 
            # Slightly expand clip to avoid edge-case failures with floating point bboxes
            clip_expanded = fitz.Rect(clip_rect.x0 - 2, clip_rect.y0 - 2, clip_rect.x1 + 2, clip_rect.y1 + 2)
            
            hit_rects = page.search_for(search_query, clip=clip_expanded)
            
            if not hit_rects and "\n" in highlight_text:
                # 2. Multi-line selection fallback: Search for each line separately
                lines = [l.strip() for l in highlight_text.split("\n") if l.strip()]
                for line in lines:
                    line_hits = page.search_for(line, clip=clip_expanded)
                    hit_rects.extend(line_hits)
            
            if not hit_rects:
                self.app.show_toast("Info", "Could not find precise coordinates for selection.", is_error=True)
                # Don't fallback to entire block anymore as it confuses the user
                return 
        else:
            # Default: Highlight the entire block
            hit_rects = [fitz.Rect(obj["bbox"])]

        # 3. Apply the highlight
        for rect in hit_rects:
            cmd = AnnotationCommand(self.state.doc, self.state.current_page_index, list(rect), "highlight")
            self.state.push_command(cmd)
            
        self.render_page()
        msg = f"Highlighted selection" if highlight_text else "Highlighted block"
        self.app.show_toast("Success", msg)

    def apply_text_change(self, obj, new_text, force_bold=None, force_underline=None):
        try:
            # Check if text actually changed (or style override)
            if new_text == obj.get("text", "") and force_bold is None and force_underline is None:
                return

            cmd = ReplaceTextCommand(self.engine, self.state.current_page_index, obj, obj["text"], new_text, 
                                     force_bold=force_bold, force_underline=force_underline)
            success = self.state.push_command(cmd)
            
            if success:
                self.render_page()
                if cmd.last_warning:
                    self.app.show_toast("Warning", cmd.last_warning)
                else:
                    self.app.show_toast("Success", "Text updated successfully")
                
                # Clear selection after update to avoid confusion
                self.state.selected_object = None
                self.clear_properties()
        except Exception as e:
            self.app.show_toast("Error", f"Failed to update text: {str(e)}", is_error=True)

    def delete_pdf_object(self, obj):
        from core.pdf_editor_engine import PDFEditorEngine # just to be sure
        self.engine.delete_object(self.state.current_page_index, obj)
        self.render_page()
        self.clear_properties()


    def clear_all_page_overlays(self):
        page_idx = self.state.current_page_index
        if page_idx in self.state.page_overlays:
            self.state.page_overlays[page_idx] = []
            self.render_page()
            self.clear_properties()

    def show_context_menu(self, event):
        # Select the object under mouse first
        self.on_canvas_click(event)
        if not self.state.selected_overlay: return
        
        from tkinter import Menu
        m = Menu(self, tearoff=0)
        m.add_command(label="Duplicate", command=self.duplicate_overlay)
        m.add_separator()
        m.add_command(label="Delete", command=self.delete_overlay)
        m.tk_popup(event.x_root, event.y_root)

    def update_ov_opacity(self, val):
        if self.state.selected_overlay:
            self.state.selected_overlay["opacity"] = float(val)
            self.render_overlays()

    def update_ov_rotation(self, val):
        if self.state.selected_overlay:
            self.state.selected_overlay["rotation"] = int(val)
            self.render_overlays()

    def update_ov_width(self, val):
        if self.state.selected_overlay:
            ov = self.state.selected_overlay
            ov["bbox"][2] = ov["bbox"][0] + float(val)
            self.render_overlays()

    def update_ov_height(self, val):
        if self.state.selected_overlay:
            ov = self.state.selected_overlay
            ov["bbox"][3] = ov["bbox"][1] + float(val)
            self.render_overlays()

    def delete_overlay(self):
        if self.state.selected_overlay:
            cmd = DeleteOverlayCommand(self.state, self.state.current_page_index, self.state.selected_overlay)
            self.state.push_command(cmd)
            self.state.selected_overlay = None
            self.render_page()
            self.update_properties_panel()

    def update_ov_text(self, new_text):
        if self.state.selected_overlay:
            self.state.selected_overlay["text"] = new_text
            self.render_overlays()
            self.update_properties_panel()

    def bring_overlay_forward(self):
        idx = self.state.current_page_index
        ovs = self.state.page_overlays.get(idx, [])
        if self.state.selected_overlay in ovs:
            curr_i = ovs.index(self.state.selected_overlay)
            if curr_i < len(ovs) - 1:
                ovs[curr_i], ovs[curr_i+1] = ovs[curr_i+1], ovs[curr_i]
                self.render_overlays()
                self.update_properties_panel()

    def send_overlay_backward(self):
        idx = self.state.current_page_index
        ovs = self.state.page_overlays.get(idx, [])
        if self.state.selected_overlay in ovs:
            curr_i = ovs.index(self.state.selected_overlay)
            if curr_i > 0:
                ovs[curr_i], ovs[curr_i-1] = ovs[curr_i-1], ovs[curr_i]
                self.render_overlays()
                self.update_properties_panel()

    def duplicate_overlay(self):
        if self.state.selected_overlay:
            new_ov = self.state.selected_overlay.copy()
            new_ov["bbox"] = [b + 10 for b in new_ov["bbox"]]
            cmd = AddOverlayCommand(self.state, self.state.current_page_index, new_ov)
            self.state.push_command(cmd)
            self.render_page()

    def save_pdf(self):
        if not self.state.doc: return
        from tkinter import filedialog
        import os
        
        # Default to original filename if possible
        init_file = os.path.basename(self.state.current_path) if self.state.current_path else "signed_doc.pdf"
        path = filedialog.asksaveasfilename(defaultextension=".pdf", 
                                            initialfile=init_file,
                                            title="Save PDF As")
        if path:
            try:
                # Engine now handles overlays
                if self.engine.save_pdf(path, page_overlays=self.state.page_overlays):
                    self.app.show_toast("Success", f"File saved successfully to:\n{os.path.basename(path)}")
                else:
                    self.app.show_toast("Error", "Failed to save PDF. Check if file is open elsewhere.", is_error=True)
            except Exception as e:
                self.app.show_toast("Error", f"Save failed: {str(e)}", is_error=True)

    def zoom_in(self):
        self.state.zoom_level += 0.2
        self.render_page()
        self.update_properties_panel()

    def zoom_out(self):
        if self.state.zoom_level > 0.4:
            self.state.zoom_level -= 0.2
            self.render_page()
            self.update_properties_panel()

    def undo_action(self):
        if self.state.undo():
            self.load_pdf_data() # Refresh thumbnails and render current page
            self.update_button_states()

    def redo_action(self):
        if self.state.redo():
            self.load_pdf_data() # Refresh thumbnails and render current page
            self.update_button_states()

    def rotate_current_page(self):
        cmd = RotateCommand(self.state.doc, self.state.current_page_index)
        self.state.push_command(cmd)
        self.load_pdf_data() # Full refresh for thumbnails + preview
        self.app.show_toast("Success", "Page rotated")

    def delete_current_page(self):
        import tkinter.messagebox as tkmb
        if tkmb.askyesno("Confirm Delete", "Delete this page?"):
            cmd = DeletePageCommand(self.state.doc, self.state.current_page_index)
            self.state.push_command(cmd)
            self.state.current_page_index = max(0, self.state.current_page_index - 1)
            self.load_pdf_data()

    def duplicate_current_page(self):
        cmd = DuplicatePageCommand(self.state.doc, self.state.current_page_index)
        self.state.push_command(cmd)
        self.load_pdf_data()
        self.app.show_toast("Success", "Page duplicated")

    def clear_properties(self):
        self.state.selected_object = None
        self.state.selected_overlay = None
        self.update_properties_panel()

