import customtkinter as ctk
from ui.theme import Theme
import threading
import time

def _BODY_FONT(size=12, bold=False):
    return ctk.CTkFont(family=Theme.FONT_FAMILY, size=size, weight="bold" if bold else "normal")

_MUTED = Theme.TEXT_MUTED
_ACCENT = Theme.ACCENT_BLUE

class LicenseServerView(ctk.CTkFrame):
    def __init__(self, master, app_window, **kwargs):
        super().__init__(master, fg_color=Theme.BG_PRIMARY, **kwargs)
        self.app = app_window
        self.mgr = getattr(self.app, 'seat_manager', None)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) 
        
        # Header
        hdr_frame = ctk.CTkFrame(self, fg_color="transparent")
        hdr_frame.pack(fill="x", padx=40, pady=(20, 10))
        
        lbl_hdr = ctk.CTkLabel(hdr_frame, text="Office Network Seats", 
                               font=ctk.CTkFont(family=Theme.FONT_FAMILY, size=24, weight="bold"))
        lbl_hdr.pack(side="left")
        
        self.lbl_status = ctk.CTkLabel(hdr_frame, text="● SCANNING LAN", text_color=_ACCENT,
                                       font=ctk.CTkFont(weight="bold"))
        self.lbl_status.pack(side="right", pady=5)

        # Seat Overview Card
        self.stats_frame = ctk.CTkFrame(self, fg_color=Theme.BG_SECONDARY, corner_radius=10)
        self.stats_frame.pack(fill="x", padx=40, pady=10)
        
        self.lbl_seats = ctk.CTkLabel(self.stats_frame, text="Network Seats: 0 / 0",
                                      font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_seats.pack(pady=15)
        
        self.lbl_msg = ctk.CTkLabel(self.stats_frame, text="Waiting for discovery...", font=_BODY_FONT(11), text_color=_MUTED)
        self.lbl_msg.pack(pady=(0, 15))

        # Warning Banner (hidden by default)
        self.warning_frame = ctk.CTkFrame(self, fg_color="#e74c3c", corner_radius=8)
        self.warning_lbl = ctk.CTkLabel(self.warning_frame, 
                                         text="⛔ SEAT LIMIT EXCEEDED — Some PCs will have restricted functionality",
                                         font=_BODY_FONT(12, bold=True), text_color="white")
        self.warning_lbl.pack(pady=10, padx=20)
        # Don't pack warning_frame yet — shown conditionally

        # Active Users Table Header
        tbl_hdr = ctk.CTkFrame(self, fg_color="transparent")
        tbl_hdr.pack(fill="x", padx=40, pady=(10, 0))
        
        ctk.CTkLabel(tbl_hdr, text="Running Instances on Local Network", 
                     font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
        
        self.lbl_count = ctk.CTkLabel(tbl_hdr, text="", font=_BODY_FONT(10), text_color=_MUTED)
        self.lbl_count.pack(side="right", padx=5)
        
        # Table column headers
        col_hdr = ctk.CTkFrame(self, fg_color=Theme.BG_SECONDARY, corner_radius=6)
        col_hdr.pack(fill="x", padx=40, pady=(5, 0))
        
        ctk.CTkLabel(col_hdr, text="PC Name", width=200, anchor="w", 
                     font=_BODY_FONT(10, bold=True), text_color=_MUTED).pack(side="left", padx=15, pady=6)
        ctk.CTkLabel(col_hdr, text="IP Address", width=150, anchor="w", 
                     font=_BODY_FONT(10, bold=True), text_color=_MUTED).pack(side="left", padx=10, pady=6)
        ctk.CTkLabel(col_hdr, text="Machine ID", width=200, anchor="w", 
                     font=_BODY_FONT(10, bold=True), text_color=_MUTED).pack(side="left", padx=10, pady=6)
        ctk.CTkLabel(col_hdr, text="Status", width=80, 
                     font=_BODY_FONT(10, bold=True), text_color=_MUTED).pack(side="right", padx=20, pady=6)
        
        self.table_frame = ctk.CTkScrollableFrame(self, fg_color=Theme.BG_SECONDARY, height=250)
        self.table_frame.pack(fill="x", padx=40, pady=(0, 5))
        
        # Peer-to-Peer Info Note
        ctk.CTkLabel(self, text="💡 Note: Seat tracking is decentralized. All PCs coordinate automatically via LAN broadcasts.", 
                     font=_BODY_FONT(10), text_color=_MUTED).pack(anchor="w", padx=45, pady=10)

        self.update_loop()

    def update_loop(self):
        if not self.winfo_exists(): return
        
        if self.mgr:
            # Update Status text and color
            color = "#2ecc71" if self.mgr.has_seat else "#e74c3c"
            status = "LICENSE ACTIVE" if self.mgr.has_seat else "SEATS EXCEEDED"
            self.lbl_status.configure(text=f"● {status}", text_color=color)
            
            # Update Seat Count
            count = self.mgr.get_peer_count()
            max_s = self.mgr.max_seats
            self.lbl_seats.configure(text=f"Network Usage: {count} / {max_s}")
            self.lbl_msg.configure(text=self.mgr.status_msg, text_color=color if self.mgr.is_over_limit else "white")
            
            # Show/hide warning banner
            if self.mgr.is_over_limit:
                self.warning_frame.pack(fill="x", padx=40, pady=(0, 5), after=self.stats_frame)
            else:
                self.warning_frame.pack_forget()
            
            # Update Table
            for widget in self.table_frame.winfo_children():
                widget.destroy()
            
            peers = self.mgr.get_active_list()
            self.lbl_count.configure(text=f"{len(peers)} instance(s) detected")
            
            if not peers:
                ctk.CTkLabel(self.table_frame, text="No active connections found on LAN", text_color="gray").pack(pady=20)
            else:
                # Sort: this PC first, then alphabetical by hostname
                peers.sort(key=lambda p: (0 if p["machine_id"] == self.mgr.machine_id else 1, p.get("hostname", "")))
                
                for peer in peers:
                    mid = peer["machine_id"]
                    hostname = peer.get("hostname", "Unknown")
                    ip = peer.get("ip", "?")
                    is_me = mid == self.mgr.machine_id
                    
                    row = ctk.CTkFrame(self.table_frame, 
                                       fg_color=Theme.BG_PRIMARY if is_me else "transparent", 
                                       corner_radius=6)
                    row.pack(fill="x", pady=2, padx=5)
                    
                    # PC Name (hostname)
                    me_tag = " (This PC)" if is_me else ""
                    ctk.CTkLabel(row, text=f"💻 {hostname}{me_tag}", width=200, anchor="w", 
                                font=_BODY_FONT(12, bold=is_me)).pack(side="left", padx=15, pady=8)
                    
                    # IP Address
                    ctk.CTkLabel(row, text=ip, width=150, anchor="w",
                                font=_BODY_FONT(11), text_color=_MUTED).pack(side="left", padx=10, pady=8)
                    
                    # Machine ID
                    ctk.CTkLabel(row, text=mid, width=200, anchor="w",
                                font=_BODY_FONT(10), text_color=_MUTED).pack(side="left", padx=10, pady=8)
                    
                    # Status
                    status_lbl = ctk.CTkLabel(row, text="Active", text_color="#2ecc71", font=_BODY_FONT(11))
                    status_lbl.pack(side="right", padx=20)

        self.after(3000, self.update_loop)
