"""
GUI Styles and Themes
Based on Auto-Password.jpg design
"""


COLORS = {
    "bg_gradient_start": "#4158D0",
    "bg_gradient_mid": "#C850C0", 
    "bg_gradient_end": "#FFCC70",
    "bg_dark": "#1a1a2e",
    "bg_medium": "#16213e",
    "bg_light": "#0f3460",
    "accent_purple": "#8B5CF6",
    "accent_blue": "#3B82F6",
    "accent_teal": "#14B8A6",
    "accent_green": "#10B981",
    "accent_orange": "#F59E0B",
    "text_white": "#FFFFFF",
    "text_gray": "#9CA3AF",
    "success": "#10B981",
    "error": "#EF4444",
    "warning": "#F59E0B"
}


FONTS = {
    "title": ("Arial", 24, "bold"),
    "subtitle": ("Arial", 18, "bold"),
    "heading": ("Arial", 16, "bold"),
    "body": ("Arial", 12),
    "body_bold": ("Arial", 12, "bold"),
    "small": ("Arial", 10),
    "button": ("Arial", 14, "bold")
}


BUTTON_STYLES = {
    "primary": {
        "fg_color": COLORS["accent_purple"],
        "hover_color": COLORS["accent_blue"],
        "text_color": COLORS["text_white"],
        "corner_radius": 10,
        "height": 40
    },
    "success": {
        "fg_color": COLORS["accent_green"],
        "hover_color": COLORS["accent_teal"],
        "text_color": COLORS["text_white"],
        "corner_radius": 10,
        "height": 40
    },
    "danger": {
        "fg_color": COLORS["error"],
        "hover_color": "#DC2626",
        "text_color": COLORS["text_white"],
        "corner_radius": 10,
        "height": 40
    },
    "secondary": {
        "fg_color": COLORS["bg_light"],
        "hover_color": COLORS["bg_medium"],
        "text_color": COLORS["text_white"],
        "corner_radius": 10,
        "height": 40
    }
}


ENTRY_STYLES = {
    "fg_color": COLORS["bg_dark"],
    "border_color": COLORS["accent_purple"],
    "text_color": COLORS["text_white"],
    "corner_radius": 8,
    "height": 40
}


FRAME_STYLES = {
    "fg_color": COLORS["bg_medium"],
    "corner_radius": 15,
    "border_width": 2,
    "border_color": COLORS["accent_purple"]
}


WINDOW_SIZE = {
    "width": 900,
    "height": 650
}
