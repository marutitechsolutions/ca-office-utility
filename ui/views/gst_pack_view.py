"""
GST Pack Builder — Main UI View
Premium tabbed workflow for building GST submission packs.
"""

import customtkinter as ctk
from customtkinter import filedialog
import tkinter as tk
import os
import re
import threading
import logging

from ui.theme import Theme
from ui.components import DragDropArea
from services.gst_pack.models import (
    PackProject, PackType, MatterDetails, DocumentItem, PackSettings,
    AnnexureStyle, PageNumberFormat, PageNumberPosition, DOCUMENT_CATEGORIES,
)
from services.gst_pack.pack_profiles import get_checklist, get_recommended_order
from services.gst_pack.validation_service import validate_pack, has_critical_missing, get_summary_text
from services.gst_pack.pack_builder_service import build_pack, count_pdf_pages, get_pack_summary
from services.gst_pack.pack_storage_service import save_draft, load_draft
from services.gst_pack.notice_extractor_service import extract_matter_details

logger = logging.getLogger(__name__)

# ─── Shared styling helpers ───
_CARD_KW = dict(fg_color=Theme.BG_SECONDARY, corner_radius=Theme.CORNER_RADIUS,
                border_width=Theme.BORDER_WIDTH, border_color=Theme.BORDER_COLOR)
_HDR_FONT = lambda sz=14: ctk.CTkFont(family=Theme.FONT_FAMILY, size=sz, weight="bold")
_BODY_FONT = lambda sz=12: ctk.CTkFont(family=Theme.FONT_FAMILY, size=sz)
_MUTED = Theme.TEXT_MUTED
_ACCENT = Theme.ACCENT_BLUE
_HOVER = Theme.ACCENT_HOVER
_GREEN = Theme.ACCENT_GREEN
_AMBER = Theme.ACCENT_AMBER
_BG1 = Theme.BG_PRIMARY
_BG2 = Theme.BG_SECONDARY


class GstPackView(ctk.CTkFrame):
    """Full GST Pack Builder module UI."""

    TAB_NAMES = ["Pack Type", "Matter Details", "Documents", "Settings", "Validation", "Generate"]

    def __init__(self, master, app_window, **kwargs):
        super().__init__(master, fg_color=_BG1, **kwargs)
        self.app = app_window
        self.project = PackProject()
        self.project.settings.output_folder = os.path.join(os.path.expanduser("~"), "Documents")
        self._current_tab = 0

        # Main layout
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_tab_area()
        self._build_bottom_bar()
        self._show_tab(0)

    # ──────────────────────── HEADER ────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=5, pady=(0, 5))
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="📑", font=ctk.CTkFont(size=28)).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkLabel(hdr, text="GST Pack Builder", font=_HDR_FONT(22), anchor="w").grid(row=0, column=1, sticky="w")

        # Tab buttons
        tabs_fr = ctk.CTkFrame(hdr, fg_color="transparent")
        tabs_fr.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._tab_buttons = []
        for i, name in enumerate(self.TAB_NAMES):
            b = ctk.CTkButton(tabs_fr, text=name, width=110, height=32, corner_radius=8,
                              fg_color=_BG2, hover_color=_HOVER, text_color=_MUTED,
                              font=_BODY_FONT(12), command=lambda idx=i: self._show_tab(idx))
            b.pack(side="left", padx=2)
            self._tab_buttons.append(b)

    # ──────────────────────── TAB CONTAINER ────────────────────────
    def _build_tab_area(self):
        self._tab_container = ctk.CTkFrame(self, fg_color="transparent")
        self._tab_container.grid(row=1, column=0, sticky="nsew", padx=5)
        self._tab_container.grid_rowconfigure(0, weight=1)
        self._tab_container.grid_columnconfigure(0, weight=1)

    def _show_tab(self, idx):
        self._current_tab = idx
        for i, b in enumerate(self._tab_buttons):
            if i == idx:
                b.configure(fg_color=_ACCENT, text_color="white")
            else:
                b.configure(fg_color=_BG2, text_color=_MUTED)
        for w in self._tab_container.winfo_children():
            w.destroy()

        builders = [self._tab_pack_type, self._tab_matter, self._tab_documents,
                     self._tab_settings, self._tab_validation, self._tab_generate]
        builders[idx]()

    # ──────────────────────── BOTTOM BAR ────────────────────────
    def _build_bottom_bar(self):
        bar = ctk.CTkFrame(self, fg_color=_BG2, corner_radius=10, height=48)
        bar.grid(row=2, column=0, sticky="ew", padx=5, pady=(5, 0))
        bar.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(bar, text="💾 Save Draft", width=120, height=34, corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR,
                      hover_color=_BG1, font=_BODY_FONT(12), command=self._save_draft
                      ).grid(row=0, column=0, padx=(10, 4), pady=7)
        ctk.CTkButton(bar, text="📂 Load Draft", width=120, height=34, corner_radius=8,
                      fg_color="transparent", border_width=1, border_color=Theme.BORDER_COLOR,
                      hover_color=_BG1, font=_BODY_FONT(12), command=self._load_draft
                      ).grid(row=0, column=1, padx=4, pady=7)

        self._status_lbl = ctk.CTkLabel(bar, text="Ready", font=_BODY_FONT(11), text_color=_MUTED, anchor="e")
        self._status_lbl.grid(row=0, column=2, sticky="e", padx=(10, 15))

    # ════════════════════════════════════════════════════════════
    # TAB 1 — PACK TYPE
    # ════════════════════════════════════════════════════════════
    def _tab_pack_type(self):
        scroll = ctk.CTkScrollableFrame(self._tab_container, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(scroll, text="Select Pack Type", font=_HDR_FONT(16)).pack(anchor="w", pady=(10, 15))
        self._pack_type_var = tk.StringVar(value=self.project.pack_type)
        for pt in PackType:
            fr = ctk.CTkFrame(scroll, **_CARD_KW)
            fr.pack(fill="x", pady=4, padx=2)
            rb = ctk.CTkRadioButton(fr, text=pt.value, variable=self._pack_type_var,
                                    value=pt.value, font=_BODY_FONT(13),
                                    command=self._on_pack_type_change)
            rb.pack(padx=15, pady=12, anchor="w")

    def _on_pack_type_change(self):
        self.project.pack_type = self._pack_type_var.get()
        self._status_lbl.configure(text=f"Pack type: {self.project.pack_type}")

    # ════════════════════════════════════════════════════════════
    # TAB 2 — MATTER DETAILS
    # ════════════════════════════════════════════════════════════
    def _tab_matter(self):
        scroll = ctk.CTkScrollableFrame(self._tab_container, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(1, weight=1)

        # Header row with extract button
        hdr_fr = ctk.CTkFrame(scroll, fg_color="transparent")
        hdr_fr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(10, 8))
        ctk.CTkLabel(hdr_fr, text="Matter / Case Details", font=_HDR_FONT(16)).pack(side="left")
        ctk.CTkButton(hdr_fr, text="📄 Extract from Notice / Order PDF", width=260, height=34,
                      corner_radius=8, fg_color=_AMBER, hover_color="#d97706",
                      text_color="black", font=_HDR_FONT(12),
                      command=self._extract_from_notice).pack(side="right", padx=(15, 0))

        self._extract_status_lbl = ctk.CTkLabel(scroll, text="", font=_BODY_FONT(11),
                                                 text_color=_GREEN)
        self._extract_status_lbl.grid(row=0, column=0, columnspan=2, sticky="e", padx=10)

        self._matter_entries = {}
        fields = [
            ("client_name", "Client Name *"), ("trade_name", "Trade Name"),
            ("gstin", "GSTIN *"), ("matter_type", "Matter Type"),
            ("notice_reference", "Notice / SCN Reference"), ("notice_date", "Notice Date"),
            ("section_rule", "Section / Rule"), ("authority_name", "Authority / Officer"),
            ("period", "Tax Period"), ("place", "Place / Office"),
            ("submission_date", "Submission Date"), ("appeal_no", "Appeal No."),
            ("order_no", "Order No."), ("prepared_by", "Prepared By"),
            ("remarks", "Remarks / Notes"),
        ]
        for r, (key, label) in enumerate(fields, start=1):
            ctk.CTkLabel(scroll, text=label, font=_BODY_FONT(12), text_color=_MUTED
                         ).grid(row=r, column=0, sticky="e", padx=(10, 8), pady=5)
            ent = ctk.CTkEntry(scroll, height=34, corner_radius=8, border_color=Theme.BORDER_COLOR,
                               fg_color=_BG1, font=_BODY_FONT(12))
            ent.grid(row=r, column=1, sticky="ew", padx=(0, 10), pady=5)
            current = getattr(self.project.matter_details, key, "")
            if current:
                ent.insert(0, current)
            self._matter_entries[key] = ent

        # Buttons row
        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.grid(row=len(fields) + 1, column=0, columnspan=2, pady=20)
        ctk.CTkButton(btn_row, text="Save Details", height=38, corner_radius=8,
                      fg_color=_ACCENT, hover_color=_HOVER, font=_HDR_FONT(13),
                      command=self._save_matter).pack(side="left", padx=8)

    def _save_matter(self):
        for key, ent in self._matter_entries.items():
            setattr(self.project.matter_details, key, ent.get().strip())
        self._status_lbl.configure(text="Matter details saved ✓")

    def _extract_from_notice(self):
        """Extract matter details from a notice/order PDF."""
        path = filedialog.askopenfilename(
            title="Select Notice / Order PDF",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            extracted = extract_matter_details(path)
            # Fill fields that were extracted (non-empty) into UI entries
            filled_count = 0
            for key, ent in self._matter_entries.items():
                val = getattr(extracted, key, "")
                if val:
                    ent.delete(0, "end")
                    ent.insert(0, val)
                    filled_count += 1
            # Also save to model
            for key in self._matter_entries:
                val = getattr(extracted, key, "")
                if val:
                    setattr(self.project.matter_details, key, val)
            msg = f"✓ Extracted {filled_count} field(s) from {os.path.basename(path)}"
            self._extract_status_lbl.configure(text=msg)
            self._status_lbl.configure(text=msg)
        except Exception as e:
            self.app.show_toast("Extraction Error", str(e), is_error=True)

    # ════════════════════════════════════════════════════════════
    # TAB 3 — DOCUMENTS
    # ════════════════════════════════════════════════════════════
    def _tab_documents(self):
        container = ctk.CTkFrame(self._tab_container, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # Top: Add files area
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)

        self._dnd_area = DragDropArea(top, on_drop_callback=self._on_files_dropped,
                                      title="Drop PDF Files Here", height=100)
        self._dnd_area.grid(row=0, column=0, sticky="ew", padx=2, pady=(5, 8))

        # Document list
        self._doc_scroll = ctk.CTkScrollableFrame(container, fg_color="transparent")
        self._doc_scroll.grid(row=1, column=0, sticky="nsew", padx=2)
        self._rebuild_doc_list()

    def _on_files_dropped(self, files):
        pdf_files = [f for f in files if f.lower().endswith('.pdf')]
        if not pdf_files:
            self.app.show_toast("Error", "Please add PDF files only.", is_error=True)
            return
        for fp in pdf_files:
            if any(d.file_path == fp for d in self.project.documents):
                continue
            doc = DocumentItem(
                file_path=fp,
                title=os.path.splitext(os.path.basename(fp))[0],
                category="Other Documents",
                order_index=len(self.project.documents),
                estimated_pages=count_pdf_pages(fp),
            )
            self.project.documents.append(doc)
        self._rebuild_doc_list()
        self._status_lbl.configure(text=f"{len(self.project.documents)} document(s) in pack")

    def _rebuild_doc_list(self):
        for w in self._doc_scroll.winfo_children():
            w.destroy()
        if not self.project.documents:
            ctk.CTkLabel(self._doc_scroll, text="No documents added yet",
                         font=_BODY_FONT(12), text_color=_MUTED).pack(pady=40)
            return

        for i, doc in enumerate(self.project.documents):
            self._build_doc_row(i, doc)

    def _build_doc_row(self, idx, doc):
        row = ctk.CTkFrame(self._doc_scroll, **_CARD_KW, height=70)
        row.pack(fill="x", pady=3, padx=2)
        row.grid_columnconfigure(1, weight=1)

        # Index label
        ctk.CTkLabel(row, text=f"#{idx+1}", width=35, font=_HDR_FONT(12),
                     text_color=_MUTED).grid(row=0, column=0, rowspan=2, padx=(10, 5), pady=8)

        # Title entry
        title_ent = ctk.CTkEntry(row, height=30, corner_radius=6, fg_color=_BG1,
                                 border_color=Theme.BORDER_COLOR, font=_BODY_FONT(12))
        title_ent.insert(0, doc.title)
        title_ent.grid(row=0, column=1, sticky="ew", padx=4, pady=(8, 2))
        title_ent.bind("<FocusOut>", lambda e, d=doc, ent=title_ent: setattr(d, 'title', ent.get().strip()))

        # Category + controls row
        ctrl = ctk.CTkFrame(row, fg_color="transparent")
        ctrl.grid(row=1, column=1, sticky="ew", padx=4, pady=(2, 8))

        cat_var = ctk.StringVar(value=doc.category)
        cat_menu = ctk.CTkOptionMenu(ctrl, variable=cat_var, values=DOCUMENT_CATEGORIES,
                                      width=180, height=28, corner_radius=6,
                                      fg_color=_BG1, button_color=_ACCENT, font=_BODY_FONT(11),
                                      command=lambda v, d=doc: setattr(d, 'category', v))
        cat_menu.pack(side="left", padx=(0, 6))

        pg_lbl = ctk.CTkLabel(ctrl, text=f"{doc.estimated_pages} pg", font=_BODY_FONT(11), text_color=_MUTED)
        pg_lbl.pack(side="left", padx=4)

        # Buttons column
        btn_fr = ctk.CTkFrame(row, fg_color="transparent")
        btn_fr.grid(row=0, column=2, rowspan=2, padx=(4, 8), pady=8)

        if idx > 0:
            ctk.CTkButton(btn_fr, text="▲", width=30, height=26, corner_radius=6,
                          fg_color="transparent", hover_color=_BG1, text_color=_MUTED,
                          command=lambda i=idx: self._move_doc(i, -1)).pack(pady=1)
        if idx < len(self.project.documents) - 1:
            ctk.CTkButton(btn_fr, text="▼", width=30, height=26, corner_radius=6,
                          fg_color="transparent", hover_color=_BG1, text_color=_MUTED,
                          command=lambda i=idx: self._move_doc(i, 1)).pack(pady=1)

        ctk.CTkButton(btn_fr, text="✕", width=30, height=26, corner_radius=6,
                      fg_color="transparent", hover_color="#e74c3c", text_color=_MUTED,
                      command=lambda i=idx: self._remove_doc(i)).pack(pady=1)

    def _move_doc(self, idx, direction):
        docs = self.project.documents
        new_idx = idx + direction
        if 0 <= new_idx < len(docs):
            docs[idx], docs[new_idx] = docs[new_idx], docs[idx]
            for i, d in enumerate(docs):
                d.order_index = i
            self._rebuild_doc_list()

    def _remove_doc(self, idx):
        self.project.documents.pop(idx)
        for i, d in enumerate(self.project.documents):
            d.order_index = i
        self._rebuild_doc_list()

    # ════════════════════════════════════════════════════════════
    # TAB 4 — SETTINGS
    # ════════════════════════════════════════════════════════════
    def _tab_settings(self):
        scroll = ctk.CTkScrollableFrame(self._tab_container, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        s = self.project.settings

        ctk.CTkLabel(scroll, text="Pack Settings", font=_HDR_FONT(16)).pack(anchor="w", pady=(10, 15))

        # Toggle switches
        toggles_card = ctk.CTkFrame(scroll, **_CARD_KW)
        toggles_card.pack(fill="x", padx=2, pady=4)

        self._sw_cover = self._add_switch(toggles_card, "Include Cover Page", s.include_cover, 0)
        self._sw_index = self._add_switch(toggles_card, "Include Index Page", s.include_index, 1)
        self._sw_annex = self._add_switch(toggles_card, "Include Annexure Labels", s.include_annexure_labels, 2)
        self._sw_pgnum = self._add_switch(toggles_card, "Include Page Numbers", s.include_page_numbers, 3)

        # Annexure style
        style_card = ctk.CTkFrame(scroll, **_CARD_KW)
        style_card.pack(fill="x", padx=2, pady=4)
        ctk.CTkLabel(style_card, text="Annexure Style", font=_HDR_FONT(13)).grid(
            row=0, column=0, padx=15, pady=(12, 5), sticky="w")
        self._annex_style_var = ctk.StringVar(value=s.annexure_style)
        for i, st in enumerate(AnnexureStyle):
            ctk.CTkRadioButton(style_card, text=st.value, variable=self._annex_style_var,
                               value=st.value, font=_BODY_FONT(12)).grid(
                row=1, column=i, padx=15, pady=(0, 5), sticky="w")
        ctk.CTkLabel(style_card, text="Custom Prefix:", font=_BODY_FONT(11), text_color=_MUTED
                     ).grid(row=2, column=0, padx=15, pady=(0, 12), sticky="e")
        self._custom_prefix_ent = ctk.CTkEntry(style_card, width=100, height=30, corner_radius=6,
                                                fg_color=_BG1, border_color=Theme.BORDER_COLOR)
        self._custom_prefix_ent.insert(0, s.custom_annexure_prefix)
        self._custom_prefix_ent.grid(row=2, column=1, padx=5, pady=(0, 12), sticky="w")

        # Page number format
        pg_card = ctk.CTkFrame(scroll, **_CARD_KW)
        pg_card.pack(fill="x", padx=2, pady=4)
        ctk.CTkLabel(pg_card, text="Page Number Format", font=_HDR_FONT(13)).pack(
            anchor="w", padx=15, pady=(12, 5))
        self._pg_fmt_var = ctk.StringVar(value=s.page_number_format)
        fmt_row = ctk.CTkFrame(pg_card, fg_color="transparent")
        fmt_row.pack(fill="x", padx=15, pady=(0, 5))
        for pf in PageNumberFormat:
            ctk.CTkRadioButton(fmt_row, text=pf.value, variable=self._pg_fmt_var,
                               value=pf.value, font=_BODY_FONT(12)).pack(side="left", padx=(0, 15))

        ctk.CTkLabel(pg_card, text="Position", font=_HDR_FONT(13)).pack(anchor="w", padx=15, pady=(5, 5))
        self._pg_pos_var = ctk.StringVar(value=s.page_number_position)
        pos_row = ctk.CTkFrame(pg_card, fg_color="transparent")
        pos_row.pack(fill="x", padx=15, pady=(0, 12))
        positions = [PageNumberPosition.BOTTOM_LEFT, PageNumberPosition.BOTTOM_CENTER,
                     PageNumberPosition.BOTTOM_RIGHT, PageNumberPosition.TOP_CENTER]
        for pp in positions:
            ctk.CTkRadioButton(pos_row, text=pp.value, variable=self._pg_pos_var,
                               value=pp.value, font=_BODY_FONT(11)).pack(side="left", padx=(0, 10))

        # Output settings
        out_card = ctk.CTkFrame(scroll, **_CARD_KW)
        out_card.pack(fill="x", padx=2, pady=4)
        out_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(out_card, text="Output Settings", font=_HDR_FONT(13)).grid(
            row=0, column=0, columnspan=3, padx=15, pady=(12, 8), sticky="w")

        ctk.CTkLabel(out_card, text="Folder:", font=_BODY_FONT(12), text_color=_MUTED
                     ).grid(row=1, column=0, padx=(15, 5), pady=5, sticky="e")
        self._out_folder_ent = ctk.CTkEntry(out_card, height=32, corner_radius=8,
                                             fg_color=_BG1, border_color=Theme.BORDER_COLOR)
        self._out_folder_ent.insert(0, s.output_folder)
        self._out_folder_ent.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(out_card, text="Browse", width=70, height=32, corner_radius=8,
                      fg_color=_ACCENT, hover_color=_HOVER, font=_BODY_FONT(12),
                      command=self._browse_output_folder).grid(row=1, column=2, padx=(5, 15), pady=5)

        ctk.CTkLabel(out_card, text="File Name:", font=_BODY_FONT(12), text_color=_MUTED
                     ).grid(row=2, column=0, padx=(15, 5), pady=(5, 15), sticky="e")
        self._out_name_ent = ctk.CTkEntry(out_card, height=32, corner_radius=8, fg_color=_BG1,
                                           border_color=Theme.BORDER_COLOR,
                                           placeholder_text="e.g. GST_Reply_Pack.pdf")
        if s.output_filename:
            self._out_name_ent.insert(0, s.output_filename)
        self._out_name_ent.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(5, 15), pady=(5, 15))

        # Save settings button
        ctk.CTkButton(scroll, text="Save Settings", height=38, corner_radius=8,
                      fg_color=_ACCENT, hover_color=_HOVER, font=_HDR_FONT(13),
                      command=self._save_settings).pack(pady=15)

    def _add_switch(self, parent, text, value, row):
        sw = ctk.CTkSwitch(parent, text=text, font=_BODY_FONT(12), onvalue=True, offvalue=False)
        if value:
            sw.select()
        sw.grid(row=row, column=0, padx=15, pady=8, sticky="w")
        return sw

    def _browse_output_folder(self):
        d = filedialog.askdirectory(title="Select Output Folder")
        if d:
            self._out_folder_ent.delete(0, "end")
            self._out_folder_ent.insert(0, d)

    def _save_settings(self):
        s = self.project.settings
        s.include_cover = self._sw_cover.get()
        s.include_index = self._sw_index.get()
        s.include_annexure_labels = self._sw_annex.get()
        s.include_page_numbers = self._sw_pgnum.get()
        s.annexure_style = self._annex_style_var.get()
        s.custom_annexure_prefix = self._custom_prefix_ent.get().strip() or "PB"
        s.page_number_format = self._pg_fmt_var.get()
        s.page_number_position = self._pg_pos_var.get()
        s.output_folder = self._out_folder_ent.get().strip()
        s.output_filename = self._out_name_ent.get().strip()
        self._status_lbl.configure(text="Settings saved ✓")

    # ════════════════════════════════════════════════════════════
    # TAB 5 — VALIDATION & PREVIEW
    # ════════════════════════════════════════════════════════════
    def _tab_validation(self):
        scroll = ctk.CTkScrollableFrame(self._tab_container, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(scroll, text="Validation & Pack Preview", font=_HDR_FONT(16)).pack(
            anchor="w", pady=(10, 15))

        # Summary card
        summary = get_pack_summary(self.project)
        sum_card = ctk.CTkFrame(scroll, **_CARD_KW)
        sum_card.pack(fill="x", padx=2, pady=4)
        sum_info = (f"Client: {summary['client_name']}   |   GSTIN: {summary['gstin']}   |   "
                    f"Pack: {summary['pack_type']}\n"
                    f"Annexures: {summary['total_annexures']}   |   "
                    f"Est. Pages: {summary['estimated_pages']}   |   "
                    f"Prepared By: {summary['prepared_by']}")
        ctk.CTkLabel(sum_card, text=sum_info, font=_BODY_FONT(11), text_color=_MUTED,
                     justify="left", wraplength=700).pack(padx=15, pady=12, anchor="w")

        # Validation checklist
        results = validate_pack(self.project.pack_type, self.project.documents)
        val_card = ctk.CTkFrame(scroll, **_CARD_KW)
        val_card.pack(fill="x", padx=2, pady=4)
        ctk.CTkLabel(val_card, text="Checklist Validation", font=_HDR_FONT(13)).pack(
            anchor="w", padx=15, pady=(12, 8))

        for r in results:
            row_fr = ctk.CTkFrame(val_card, fg_color="transparent")
            row_fr.pack(fill="x", padx=15, pady=2)
            if r.status == "ok":
                icon, color = "✅", _GREEN
            elif r.status == "missing":
                icon, color = "❌", "#e74c3c"
            else:
                icon, color = "⚪", _MUTED
            req_tag = " *" if r.required else ""
            ctk.CTkLabel(row_fr, text=f"{icon}  {r.category}{req_tag}", font=_BODY_FONT(12),
                         text_color=color, anchor="w").pack(side="left")
            ctk.CTkLabel(row_fr, text=r.message, font=_BODY_FONT(11),
                         text_color=_MUTED, anchor="e").pack(side="right")

        # Summary text
        summary_text = get_summary_text(results)
        ctk.CTkLabel(val_card, text=summary_text, font=_BODY_FONT(12), justify="left",
                     wraplength=600).pack(padx=15, pady=(10, 15), anchor="w")

        # Pack structure preview
        struct_card = ctk.CTkFrame(scroll, **_CARD_KW)
        struct_card.pack(fill="x", padx=2, pady=4)
        ctk.CTkLabel(struct_card, text="Pack Structure Preview", font=_HDR_FONT(13)).pack(
            anchor="w", padx=15, pady=(12, 8))

        order_items = []
        if self.project.settings.include_cover:
            order_items.append("📄  Cover Page")
        if self.project.settings.include_index:
            order_items.append("📋  Index of Annexures")

        included = sorted([d for d in self.project.documents if d.include_in_pack],
                          key=lambda d: d.order_index)
        for i, doc in enumerate(included):
            order_items.append(f"📎  {doc.title or os.path.basename(doc.file_path)}  ({doc.category})")

        if not order_items:
            order_items.append("(No items in pack)")

        for item in order_items:
            ctk.CTkLabel(struct_card, text=item, font=_BODY_FONT(12), anchor="w",
                         text_color=Theme.TEXT_PRIMARY).pack(padx=25, pady=2, anchor="w")
        ctk.CTkLabel(struct_card, text="", height=10).pack()

    # ════════════════════════════════════════════════════════════
    # TAB 6 — GENERATE
    # ════════════════════════════════════════════════════════════
    def _tab_generate(self):
        container = ctk.CTkFrame(self._tab_container, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        center = ctk.CTkFrame(container, fg_color="transparent")
        center.grid(row=0, column=0)

        ctk.CTkLabel(center, text="🏗️", font=ctk.CTkFont(size=50)).pack(pady=(30, 10))
        ctk.CTkLabel(center, text="Build Final Pack", font=_HDR_FONT(20)).pack(pady=(0, 5))

        included_count = sum(1 for d in self.project.documents if d.include_in_pack)
        ctk.CTkLabel(center, text=f"{included_count} document(s) ready for pack generation",
                     font=_BODY_FONT(13), text_color=_MUTED).pack(pady=(0, 20))

        self._gen_btn = ctk.CTkButton(center, text="⚡ Generate Pack", width=220, height=48,
                                       corner_radius=10, fg_color=_GREEN, hover_color="#059669",
                                       font=_HDR_FONT(16), command=self._start_generation)
        self._gen_btn.pack(pady=10)

        self._gen_progress = ctk.CTkProgressBar(center, width=400, progress_color=_ACCENT)
        self._gen_progress.pack(pady=10)
        self._gen_progress.set(0)

        self._gen_stage_lbl = ctk.CTkLabel(center, text="", font=_BODY_FONT(12), text_color=_MUTED)
        self._gen_stage_lbl.pack(pady=5)

        self._gen_result_lbl = ctk.CTkLabel(center, text="", font=_BODY_FONT(13), wraplength=500)
        self._gen_result_lbl.pack(pady=10)

    def _start_generation(self):
        # Auto-save settings if on settings tab vars exist
        self._sync_all_settings()

        if not self.app.check_operation_allowed():
            return

        s = self.project.settings
        # Auto-set defaults if not configured
        if not s.output_folder:
            s.output_folder = os.path.join(os.path.expanduser("~"), "Documents")
        if not s.output_filename:
            client = self.project.matter_details.client_name or "GST"
            safe_name = re.sub(r'[^\w\s\-]', '', client).strip().replace(' ', '_')[:40]
            s.output_filename = f"{safe_name}_Pack.pdf"

        included = [d for d in self.project.documents if d.include_in_pack]
        if not included:
            self.app.show_toast("Error", "No documents included in pack.", is_error=True)
            return

        # Validation warning
        results = validate_pack(self.project.pack_type, self.project.documents)
        if has_critical_missing(results):
            if not self.app.confirm("Incomplete Pack",
                    "Some required documents are missing.\nDo you want to continue anyway?"):
                return

        self._gen_btn.configure(state="disabled", text="Generating...")
        self._gen_result_lbl.configure(text="")
        threading.Thread(target=self._generation_thread, daemon=True).start()

    def _generation_thread(self):
        try:
            def progress_cb(val, msg):
                self.after(0, lambda v=val, m=msg: self._update_gen_progress(v, m))

            output = build_pack(self.project, progress_callback=progress_cb)
            self.after(500, lambda: self._on_gen_success(output))
        except Exception as e:
            self.after(0, lambda: self._on_gen_error(str(e)))

    def _update_gen_progress(self, val, msg):
        try:
            self._gen_progress.set(val)
            self._gen_stage_lbl.configure(text=msg)
        except Exception:
            pass

    def _on_gen_success(self, path):
        self._gen_btn.configure(state="normal", text="⚡ Generate Pack")
        self._gen_progress.set(1.0)
        self._gen_stage_lbl.configure(text="Complete!")
        self._gen_result_lbl.configure(text=f"✅ Pack saved to:\n{path}", text_color=_GREEN)
        self._status_lbl.configure(text="Pack generated successfully!")

    def _on_gen_error(self, msg):
        self._gen_btn.configure(state="normal", text="⚡ Generate Pack")
        self._gen_progress.set(0)
        self._gen_stage_lbl.configure(text="")
        self._gen_result_lbl.configure(text=f"❌ {msg}", text_color="#e74c3c")
        self._status_lbl.configure(text="Generation failed")

    # ════════════════════════════════════════════════════════════
    # DRAFT SAVE / LOAD
    # ════════════════════════════════════════════════════════════
    def _sync_all_settings(self):
        """Pull any unsaved UI state into project model.
        Uses try/except because widgets from non-active tabs are destroyed."""
        # Matter details
        try:
            if hasattr(self, '_matter_entries'):
                for key, ent in self._matter_entries.items():
                    setattr(self.project.matter_details, key, ent.get().strip())
        except Exception:
            pass  # Tab not active, model already has saved values

        # Settings tab widgets
        try:
            if hasattr(self, '_sw_cover'):
                s = self.project.settings
                s.include_cover = self._sw_cover.get()
                s.include_index = self._sw_index.get()
                s.include_annexure_labels = self._sw_annex.get()
                s.include_page_numbers = self._sw_pgnum.get()
                s.annexure_style = self._annex_style_var.get()
                s.custom_annexure_prefix = self._custom_prefix_ent.get().strip() or "PB"
                s.page_number_format = self._pg_fmt_var.get()
                s.page_number_position = self._pg_pos_var.get()
                s.output_folder = self._out_folder_ent.get().strip()
                s.output_filename = self._out_name_ent.get().strip()
        except Exception:
            pass  # Tab not active, model already has saved values

        # Pack type
        try:
            if hasattr(self, '_pack_type_var'):
                self.project.pack_type = self._pack_type_var.get()
        except Exception:
            pass

    def _save_draft(self):
        self._sync_all_settings()
        path = filedialog.asksaveasfilename(
            title="Save Pack Draft",
            defaultextension=".gstpack",
            filetypes=[("GST Pack Draft", "*.gstpack"), ("All Files", "*.*")],
            initialfile=f"{self.project.matter_details.client_name or 'draft'}.gstpack"
        )
        if not path:
            return
        try:
            save_draft(self.project, path)
            self._status_lbl.configure(text=f"Draft saved: {os.path.basename(path)}")
            self.app.show_toast("Saved", f"Draft saved to:\n{path}")
        except Exception as e:
            self.app.show_toast("Save Error", str(e), is_error=True)

    def _load_draft(self):
        path = filedialog.askopenfilename(
            title="Load Pack Draft",
            filetypes=[("GST Pack Draft", "*.gstpack"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            self.project = load_draft(path)
            self._status_lbl.configure(text=f"Draft loaded: {os.path.basename(path)}")
            self._show_tab(self._current_tab)  # Refresh current tab
            self.app.show_toast("Loaded", f"Draft loaded from:\n{path}")
        except Exception as e:
            self.app.show_toast("Load Error", str(e), is_error=True)
