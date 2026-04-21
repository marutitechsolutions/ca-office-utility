import customtkinter as ctk
from tkinter import Canvas, colorchooser, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os
from ui.theme import Theme
import tempfile
import datetime
import json

class SignStampDialog(ctk.CTkToplevel):
    def __init__(self, master, on_apply=None, start_tab=None):
        super().__init__(master)
        self.title("Sign & Stamp Pro")
        self.geometry("700x600")
        self.on_apply = on_apply
        self.start_tab = start_tab
        
        # New: Background removal toggle for uploads
        self.remove_bg_var = ctk.BooleanVar(value=True)
        
        self.save_dir = os.path.join(os.getcwd(), "ca_pdf_utility", "assets", "saved_items")
        if not os.path.exists(self.save_dir): 
            os.makedirs(self.save_dir)
        
        self.current_color = "black"
        self.current_thickness = 3
        self.points = []
        
        # Professional Stamp Pad Colors
        self.STAMP_PAD_COLORS = {
            "Classic Blue": "#0033fa",
            "Office Red": "#cc0000",
            "Stamp Purple": "#990099",
            "Forest Green": "#27ae60",
            "Black": "#000000"
        }
        
        self.setup_ui()
        
        # Select start tab if provided
        if self.start_tab:
            try:
                self.tabview.set(self.start_tab)
            except:
                pass
        
        # Lift and focus
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.grab_set()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Tabview for different sections
        self.tabview = ctk.CTkTabview(self, segmented_button_selected_color=Theme.ACCENT_BLUE,
                                      segmented_button_selected_hover_color=Theme.ACCENT_HOVER,
                                      segmented_button_unselected_color=Theme.BG_SECONDARY)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        
        self.tab_draw = self.tabview.add("🖋️ Draw")
        self.tab_upload = self.tabview.add("📂 Upload")
        self.tab_standard = self.tabview.add("🏷️ Standard")
        self.tab_custom = self.tabview.add("✨ Custom")
        self.tab_saved = self.tabview.add("💾 Saved")
        self.tab_date = self.tabview.add("📅 Date/Time")

        self.setup_draw_tab()
        self.setup_upload_tab()
        self.setup_standard_tab()
        self.setup_custom_tab()
        self.setup_saved_tab()
        self.setup_date_tab()

        # Bottom buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=1, column=0, pady=(0, 20))
        
        ctk.CTkButton(btn_frame, text="Close Dialog", width=150, height=36, corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR,
                      font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                      command=self.destroy).pack(side="left", padx=10)

    # --- DRAW TAB ---
    def setup_draw_tab(self):
        self.tab_draw.grid_columnconfigure(0, weight=1)
        
        # Tools frame
        tools = ctk.CTkFrame(self.tab_draw, fg_color="transparent")
        tools.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(tools, text="Color:", font=(Theme.FONT_FAMILY, 12)).pack(side="left", padx=5)
        for color in ["black", "blue", "red", "#27ae60"]:
            # Use accent blue as highlight for selection
            b_color = Theme.ACCENT_BLUE if self.current_color == color else Theme.BORDER_COLOR
            btn = ctk.CTkButton(tools, text="", width=24, height=24, corner_radius=12, fg_color=color, hover_color=color,
                                border_width=2, border_color=b_color,
                                command=lambda c=color: self.set_draw_color(c))
            btn.pack(side="left", padx=4)
            setattr(self, f"btn_color_{color.replace('#','')}", btn)

        ctk.CTkLabel(tools, text="Weight:", font=(Theme.FONT_FAMILY, 12)).pack(side="left", padx=(15, 5))
        self.thick_slider = ctk.CTkSlider(tools, from_=1, to=10, width=120, button_color=Theme.ACCENT_BLUE, command=self.set_thickness)
        self.thick_slider.set(self.current_thickness)
        self.thick_slider.pack(side="left", padx=5)

        ctk.CTkButton(tools, text="Clear", width=70, height=28, corner_radius=6, 
                      fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR,
                      font=(Theme.FONT_FAMILY, 11),
                      command=self.clear_canvas).pack(side="right", padx=5)

        # Canvas
        self.canvas_container = ctk.CTkFrame(self.tab_draw, fg_color="white", corner_radius=8, border_width=2, border_color=Theme.BORDER_COLOR)
        self.canvas_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.canvas = Canvas(self.canvas_container, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=2, pady=2)
        
        self.canvas.bind("<Button-1>", self.start_draw)
        self.canvas.bind("<B1-Motion>", self.draw)

        # Save options
        save_frame = ctk.CTkFrame(self.tab_draw, fg_color="transparent")
        save_frame.pack(fill="x", padx=10, pady=15)
        
        self.sig_name_entry = ctk.CTkEntry(save_frame, placeholder_text="Name this signature...", height=36, corner_radius=8, border_color=Theme.BORDER_COLOR)
        self.sig_name_entry.pack(side="left", fill="x", expand=True, padx=(0, 15))
        
        ctk.CTkButton(save_frame, text="✨ Save & Insert", width=140, height=36, corner_radius=8,
                      fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                      font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                      command=lambda: self.apply_draw(save=True)).pack(side="left", padx=5)
        ctk.CTkButton(save_frame, text="Insert Once", width=120, height=36, corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR,
                      font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                      command=lambda: self.apply_draw(save=False)).pack(side="left", padx=5)

    def set_draw_color(self, color):
        self.current_color = color
        color_map = {"black": "black", "blue": "blue", "red": "red", "#27ae60": "27ae60"}
        for c_key, attr_suffix in color_map.items():
            btn = getattr(self, f"btn_color_{attr_suffix}")
            b_color = Theme.ACCENT_BLUE if self.current_color == c_key else Theme.BORDER_COLOR
            btn.configure(border_color=b_color)

    def set_thickness(self, val):
        self.current_thickness = int(val)

    def start_draw(self, event):
        self.last_x, self.last_y = event.x, event.y
        self.points.append(("move", event.x, event.y, self.current_color, self.current_thickness))

    def draw(self, event):
        self.canvas.create_line(self.last_x, self.last_y, event.x, event.y, 
                                width=self.current_thickness, fill=self.current_color, 
                                capstyle="round", smooth=True)
        self.last_x, self.last_y = event.x, event.y
        self.points.append(("line", event.x, event.y, self.current_color, self.current_thickness))

    def clear_canvas(self):
        self.canvas.delete("all")
        self.points = []

    def apply_draw(self, save=False):
        if not self.points: return
        
        # Render to high-res image
        img = Image.new("RGBA", (1000, 500), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        
        # Scaling coordinates - avoid float division issues by using whole numbers where possible
        last_p = None
        for p in self.points:
            # p = (type, x, y, color, thickness)
            px, py = p[1] * 2, p[2] * 2
            if p[0] == "move": last_p = (px, py)
            else:
                if last_p: 
                    draw.line([last_p, (px, py)], fill=p[3], width=p[4]*2)
                last_p = (px, py)
        
        # Crop to content
        bbox = img.getbbox()
        if bbox: img = img.crop(bbox)
        
        temp_path = os.path.join(tempfile.gettempdir(), f"sig_{os.urandom(4).hex()}.png")
        img.save(temp_path)
        
        if save:
            name = self.sig_name_entry.get() or f"Sig_{datetime.datetime.now().strftime('%H%M%S')}"
            perm_path = os.path.join(self.save_dir, f"{name}.png")
            img.save(perm_path)
            self.save_metadata(name, "signature", perm_path)
            
        if self.on_apply:
            self.on_apply({"type": "image", "path": temp_path, "width": 150, "height": 75})
        self.destroy()

    # --- UPLOAD TAB ---
    def setup_upload_tab(self):
        ctk.CTkLabel(self.tab_upload, text="Upload your signature image (PNG/JPG)", 
                     font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=12, slant="italic"),
                     text_color=Theme.TEXT_MUTED).pack(pady=(30, 20))
        
        ctk.CTkButton(self.tab_upload, text="📁 Browse Files", width=200, height=45, corner_radius=10,
                      fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                      font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=14, weight="bold"),
                      command=self.upload_image).pack(pady=10)
        
        ctk.CTkCheckBox(self.tab_upload, text="Auto Remove Background (Best for scans)", 
                        variable=self.remove_bg_var, font=(Theme.FONT_FAMILY, 12),
                        fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER).pack(pady=(15, 0))
        
        save_toggle_f = ctk.CTkFrame(self.tab_upload, fg_color="transparent")
        save_toggle_f.pack(pady=10)
        
        self.upload_save_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(save_toggle_f, text="Save to Gallery for future use", 
                        variable=self.upload_save_var, font=(Theme.FONT_FAMILY, 11),
                        fg_color=Theme.ACCENT_BLUE).pack(side="left", padx=5)
        
        self.upload_name_entry = ctk.CTkEntry(self.tab_upload, placeholder_text="Name your stamp (e.g. My Signature)", 
                                              width=350, height=36, corner_radius=8, border_color=Theme.BORDER_COLOR)
        self.upload_name_entry.pack(pady=5)
        
        info = ctk.CTkFrame(self.tab_upload, fg_color=Theme.BG_PRIMARY, corner_radius=Theme.CORNER_RADIUS, border_width=1, border_color=Theme.BORDER_COLOR)
        info.pack(pady=30, padx=50, fill="x")
        ctk.CTkLabel(info, text="• High resolution maintained\n• Transparency preserved\n• No white boxes added", 
                     font=(Theme.FONT_FAMILY, 12), justify="left").pack(pady=15, padx=20)

    def upload_image(self):
        from tkinter import filedialog
        # Toggle topmost to ensure dialog is visible
        self.attributes("-topmost", False) 
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
        self.attributes("-topmost", True)
        if path:
            if self.on_apply:
                temp_path = os.path.join(tempfile.gettempdir(), f"upload_{os.urandom(4).hex()}.png")
                with Image.open(path) as img:
                    if self.remove_bg_var.get():
                        img = self._process_signature_image(img)
                    img.save(temp_path)
                    
                    if self.upload_save_var.get():
                        name = self.upload_name_entry.get().strip() or f"Uploaded_{datetime.datetime.now().strftime('%H%M%S')}"
                        perm_path = os.path.join(self.save_dir, f"{name}.png")
                        img.save(perm_path)
                        self.save_metadata(name, "signature", perm_path)
                        
                    w, h = img.size
                    scale = 150 / w
                    self.on_apply({"type": "image", "path": temp_path, "width": 150, "height": int(h * scale)})
            self.destroy()

    def _process_signature_image(self, pil_img):
        """Removes the background by making pixels close to white/background transparent."""
        # Ensure RGBA for transparency
        img = pil_img.convert("RGBA")
        datas = img.getdata()
        
        # Assume top-left pixel (0,0) is representative of the background color
        bg_r, bg_g, bg_b, _ = datas[0]
        
        new_data = []
        # Threshold: if a pixel is close to the background color, make it transparent
        threshold = 50 
        
        for item in datas:
            # Calculate Euclidean distance in RGB space
            dist = ((item[0] - bg_r)**2 + (item[1] - bg_g)**2 + (item[2] - bg_b)**2)**0.5
            if dist < threshold:
                # Make it fully transparent. Keep the color same or make it white.
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
                
        img.putdata(new_data)
        
        # Automatically crop to content (removes extra empty space)
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        
        return img

    # --- STANDARD STAMPS TAB ---
    def setup_standard_tab(self):
        stamps = ["PAID", "RECEIVED", "VERIFIED", "APPROVED", "CANCELLED", "SIGNED", "CONFIDENTIAL"]
        
        grid = ctk.CTkFrame(self.tab_standard, fg_color="transparent")
        grid.pack(expand=True, fill="both", padx=20, pady=20)
        
        for i, text in enumerate(stamps):
            row, col = i // 2, i % 2
            btn = ctk.CTkButton(grid, text=text, font=("Arial", 22, "bold"), height=70, corner_radius=12,
                                fg_color="transparent", border_width=3, text_color="#e74c3c", border_color="#e74c3c",
                                hover_color="#442222",
                                command=lambda t=text: self.apply_standard_stamp(t))
            btn.grid(row=row, column=col, padx=12, pady=12, sticky="nsew")
            grid.grid_columnconfigure(col, weight=1)

    def apply_standard_stamp(self, text):
        if self.on_apply:
            self.on_apply({
                "type": "text", "text": text, "color": "red", "fontsize": 30, 
                "bold": True, "width": 200, "height": 60
            })
        self.destroy()

    # --- CUSTOM TAB ---
    def setup_custom_tab(self):
        self.tab_custom.grid_columnconfigure(0, weight=1)
        
        form = ctk.CTkFrame(self.tab_custom, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=30, pady=20)
        
        ctk.CTkLabel(form, text="Company Name / Main Line:", font=(Theme.FONT_FAMILY, 12, "bold")).pack(anchor="w", pady=(10, 0))
        self.custom_main = ctk.CTkEntry(form, placeholder_text="COMPANY NAME", height=36, corner_radius=8, border_color=Theme.BORDER_COLOR)
        self.custom_main.pack(fill="x", pady=5)
        
        ctk.CTkLabel(form, text="Designation:", font=(Theme.FONT_FAMILY, 12, "bold")).pack(anchor="w", pady=(10, 0))
        self.custom_sub = ctk.CTkEntry(form, placeholder_text="Partner", height=36, corner_radius=8, border_color=Theme.BORDER_COLOR)
        self.custom_sub.pack(fill="x", pady=5)
        
        presets = ["Partner", "Proprietor", "Director", "Authorized Signatory", "Checked By", "Verified By"]
        preset_frame = ctk.CTkFrame(form, fg_color="transparent")
        preset_frame.pack(fill="x", pady=5)
        
        for i, p in enumerate(presets):
            btn = ctk.CTkButton(preset_frame, text=p, width=100, height=28, corner_radius=6,
                                fg_color=Theme.BG_PRIMARY, border_width=1, border_color=Theme.BORDER_COLOR,
                                font=(Theme.FONT_FAMILY, 10),
                                command=lambda v=p: self.set_custom_sub(v))
            btn.grid(row=i//3, column=i%3, padx=3, pady=3, sticky="nsew")
        for c in range(3): preset_frame.grid_columnconfigure(c, weight=1)

        # Style options
        style_frame = ctk.CTkFrame(form, fg_color=Theme.BG_PRIMARY, corner_radius=Theme.CORNER_RADIUS, border_width=1, border_color=Theme.BORDER_COLOR)
        style_frame.pack(fill="x", pady=20, padx=2)
        
        grid_inner = ctk.CTkFrame(style_frame, fg_color="transparent")
        grid_inner.pack(padx=15, pady=15)

        ctk.CTkLabel(grid_inner, text="Color:", font=(Theme.FONT_FAMILY, 11)).grid(row=0, column=0, padx=5, sticky="w")
        self.custom_color_name = ctk.StringVar(value="Office Red")
        ctk.CTkOptionMenu(grid_inner, values=list(self.STAMP_PAD_COLORS.keys()), variable=self.custom_color_name, width=120, height=28, corner_radius=6, button_color=Theme.ACCENT_BLUE).grid(row=0, column=1, padx=5)
        
        ctk.CTkLabel(grid_inner, text="Size:", font=(Theme.FONT_FAMILY, 11)).grid(row=0, column=2, padx=5, sticky="w")
        self.custom_size = ctk.IntVar(value=18)
        ctk.CTkSlider(grid_inner, from_=10, to=50, variable=self.custom_size, width=100, button_color=Theme.ACCENT_BLUE).grid(row=0, column=3, padx=5)

        self.custom_bold = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(grid_inner, text="Bold", variable=self.custom_bold, font=(Theme.FONT_FAMILY, 11), border_color=Theme.BORDER_COLOR, hover_color=Theme.ACCENT_BLUE).grid(row=0, column=4, padx=10)

        # Actions
        act_frame = ctk.CTkFrame(form, fg_color="transparent")
        act_frame.pack(fill="x", pady=10)
        
        self.custom_save_name = ctk.CTkEntry(act_frame, placeholder_text="Save template as...", height=36, corner_radius=8, border_color=Theme.BORDER_COLOR)
        self.custom_save_name.pack(side="left", fill="x", expand=True, padx=(0, 15))
        
        ctk.CTkButton(act_frame, text="✨ Save & Insert", width=140, height=36, corner_radius=8,
                      fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                      font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                      command=lambda: self.apply_custom(save=True)).pack(side="left", padx=5)
        ctk.CTkButton(act_frame, text="Insert Once", width=120, height=36, corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR,
                      font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                      command=lambda: self.apply_custom(save=False)).pack(side="left", padx=5)

    def set_custom_sub(self, val):
        self.custom_sub.delete(0, 'end')
        self.custom_sub.insert(0, val)

    def apply_custom(self, save=False):
        main = self.custom_main.get() or "COMPANY NAME"
        sub = self.custom_sub.get() or "Designation"
        # Increase gap between main and sub for signing space
        full_text = f"{main}\n\n\n{sub}"
        color = self.STAMP_PAD_COLORS.get(self.custom_color_name.get(), "#cc0000")
        size = self.custom_size.get()
        bold = self.custom_bold.get()
        
        if save:
            name = self.custom_save_name.get() or f"Stamp_{datetime.datetime.now().strftime('%H%M%S')}"
            self.save_metadata(name, "custom_stamp", {"text": full_text, "color": color, "size": size, "bold": bold})

        if self.on_apply:
            # Default to Right alignment (2) as requested for professional stamps
            self.on_apply({
                "type": "text", "text": full_text, "color": color, "fontsize": size, 
                "bold": bold, "width": 250, "height": 100, "align": 2, "align_str": "right"
            })
        self.destroy()

    # --- SAVED ITEMS TAB ---
    def setup_saved_tab(self):
        self.saved_scroll = ctk.CTkScrollableFrame(self.tab_saved, fg_color="transparent")
        self.saved_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.refresh_saved_items()

    def refresh_saved_items(self):
        for widget in self.saved_scroll.winfo_children(): widget.destroy()
        
        meta_path = os.path.join(self.save_dir, "metadata.json")
        if not os.path.exists(meta_path):
            ctk.CTkLabel(self.saved_scroll, text="No saved items yet.").pack(pady=20)
            return
            
        with open(meta_path, "r") as f:
            items = json.load(f)
            
        self.thumbs = {} # Keep references
        
        for name, data in items.items():
            frame = ctk.CTkFrame(self.saved_scroll, fg_color=Theme.BG_PRIMARY, corner_radius=Theme.CORNER_RADIUS, border_width=1, border_color=Theme.BORDER_COLOR)
            frame.pack(fill="x", pady=6, padx=10)
            
            # Thumbnail container
            thumb_size = (60, 40)
            thumb_frame = ctk.CTkFrame(frame, width=64, height=44, fg_color="white", corner_radius=4)
            thumb_frame.pack(side="left", padx=10, pady=8)
            thumb_frame.pack_propagate(False)
            
            if data["type"] == "signature":
                try:
                    with Image.open(data["path"]) as img:
                        img.thumbnail(thumb_size)
                        photo = ImageTk.PhotoImage(img)
                        self.thumbs[name] = photo
                        ctk.CTkLabel(thumb_frame, image=photo, text="").pack(expand=True)
                except:
                    ctk.CTkLabel(thumb_frame, text="ERR", font=(Theme.FONT_FAMILY, 9), text_color="red").pack(expand=True)
            else:
                ctk.CTkLabel(thumb_frame, text="STAMP", font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=9, weight="bold"), text_color="#cc0000").pack(expand=True)

            lbl = f"{name}\n{data['type'].replace('_', ' ').capitalize()}"
            ctk.CTkLabel(frame, text=lbl, anchor="w", font=(Theme.FONT_FAMILY, 11), justify="left").pack(side="left", padx=10, fill="x", expand=True)
            
            ctk.CTkButton(frame, text="Use", width=70, height=32, corner_radius=6, 
                          fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                          font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                          command=lambda d=data: self.use_saved_item(d)).pack(side="right", padx=5, pady=5)
            ctk.CTkButton(frame, text="Delete", width=70, height=32, corner_radius=6,
                          fg_color="transparent", border_width=1, border_color="#e74c3c", text_color="#e74c3c", hover_color="#331111",
                          font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold"),
                          command=lambda n=name: self.delete_saved_item(n)).pack(side="right", padx=5, pady=5)

    def use_saved_item(self, data):
        if self.on_apply:
            if data["type"] == "signature":
                self.on_apply({"type": "image", "path": data["path"], "width": 150, "height": 75})
            else: # custom_stamp
                content = data["content"]
                self.on_apply({
                    "type": "text", "text": content["text"], "color": content["color"], 
                    "fontsize": content["size"], "bold": content["bold"], 
                    "width": 250, "height": 80, "align": 1
                })
        self.destroy()

    def delete_saved_item(self, name):
        meta_path = os.path.join(self.save_dir, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f: items = json.load(f)
            if name in items:
                if items[name]["type"] == "signature":
                    try: os.remove(items[name]["path"])
                    except: pass
                del items[name]
                with open(meta_path, "w") as f: json.dump(items, f)
            self.refresh_saved_items()

    # --- DATE TAB ---
    def setup_date_tab(self):
        self.date_format = ctk.StringVar(value="%d-%m-%Y")
        
        frame = ctk.CTkFrame(self.tab_date, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=40, pady=20)
        
        ctk.CTkLabel(frame, text="Select Format:", font=ctk.CTkFont(family=Theme.FONT_FAMILY, weight="bold")).pack(pady=15)
        formats = [
            ("%d-%m-%Y", "DD-MM-YYYY"),
            ("%m/%d/%Y", "MM/DD/YYYY"),
            ("%d %b %Y", "DD Mon YYYY"),
            ("%d-%m-%Y %H:%M", "DD-MM-YYYY HH:MM"),
            ("%b %d, %Y %I:%M %p", "Mon DD, YYYY HH:MM AM/PM")
        ]
        
        for fmt, label in formats:
            ctk.CTkRadioButton(frame, text=label, variable=self.date_format, value=fmt, 
                               font=(Theme.FONT_FAMILY, 12), border_color=Theme.BORDER_COLOR, hover_color=Theme.ACCENT_BLUE).pack(pady=6, anchor="w", padx=20)
        
        # Style Options
        style_frame = ctk.CTkFrame(frame, fg_color=Theme.BG_PRIMARY, corner_radius=Theme.CORNER_RADIUS, border_width=1, border_color=Theme.BORDER_COLOR)
        style_frame.pack(pady=25, fill="x")
        
        ctk.CTkLabel(style_frame, text="Stamp Color:", font=(Theme.FONT_FAMILY, 11)).pack(side="left", padx=(20, 10), pady=15)
        self.date_color_name = ctk.StringVar(value="Black")
        ctk.CTkOptionMenu(style_frame, values=list(self.STAMP_PAD_COLORS.keys()), variable=self.date_color_name, 
                          width=140, height=32, corner_radius=6, button_color=Theme.ACCENT_BLUE).pack(side="left", padx=5)
            
        ctk.CTkButton(frame, text="Insert Date Stamp", height=45, corner_radius=10,
                      fg_color=Theme.ACCENT_BLUE, hover_color=Theme.ACCENT_HOVER,
                      font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=14, weight="bold"),
                      command=self.apply_date).pack(pady=10, fill="x")

    def apply_date(self):
        now = datetime.datetime.now().strftime(self.date_format.get())
        color = self.STAMP_PAD_COLORS.get(self.date_color_name.get(), "#000000")
        if self.on_apply:
            self.on_apply({
                "type": "text", "text": now, "color": color, "fontsize": 14, 
                "bold": False, "width": 150, "height": 30
            })
        self.destroy()

    # --- HELPERS ---
    def save_metadata(self, name, item_type, content):
        meta_path = os.path.join(self.save_dir, "metadata.json")
        items = {}
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f: items = json.load(f)
        
        items[name] = {
            "type": item_type,
            "path" if item_type == "signature" else "content": content,
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        
        with open(meta_path, "w") as f:
            json.dump(items, f, indent=4)

