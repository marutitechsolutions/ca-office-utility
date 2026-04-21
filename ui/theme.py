class Theme:
    # Modern Dark Pro Palette
    BG_PRIMARY = "#0B0E14"    # Deep Charcoal Background
    BG_SECONDARY = "#171B26"  # Sidebar and Cards Background
    ACCENT_BLUE = "#3B82F6"   # Electric Blue Accent
    ACCENT_HOVER = "#2563EB"  # Darker Blue for Hovers
    ACCENT_GREEN = "#10B981"  # Success/Activation Green
    ACCENT_AMBER = "#F59E0B"  # Warning/Pending Amber
    BORDER_COLOR = "#2D3748"  # Subtle Border/Stroke
    
    # Sidebar & Activation Colors
    SIDEBAR_HOVER = "#1E293B"    # Dark highlight for hover
    SIDEBAR_ACTIVE = "#3B82F6"   # Blue highlight for active
    ACTIVATION_BG = "#16A34A"    # Success Green
    ACTIVATION_HOVER = "#15803D"  # Darker Green for hover
    
    # Text Colors
    TEXT_PRIMARY = "#F8FAFC"
    TEXT_MUTED = "#94A3B8"
    TEXT_COLOR = TEXT_PRIMARY   # Alias for compatibility
    
    # Geometry
    CORNER_RADIUS = 12
    CARD_CORNER_RADIUS = 10     # Alias for compatibility
    BUTTON_CORNER_RADIUS = 8    # Alias for compatibility
    INPUT_CORNER_RADIUS = 8     # Alias for compatibility
    BORDER_WIDTH = 1
    PADDING = 20                # Standard padding for views
    
    # Fonts
    # We use a clean sans-serif stack to emulate Pro apps
    FONT_FAMILY = "Inter, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    
    @classmethod
    def apply_to_ctk(cls, ctk_module):
        """Optionally override CTK global settings if needed."""
        ctk_module.set_appearance_mode("Dark")
        ctk_module.set_default_color_theme("blue")
