"""
聊天 UI 组件：文字气泡、文件卡片、图片预览
"""

import os
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from PIL import Image, ImageTk

# 微信风格配色
BG_COLOR = "#F5F5F5"
LEFT_BG = "#EBEBEB"
WHITE = "#FFFFFF"
GREEN_BUBBLE = "#95EC69"
BLACK = "#000000"
GRAY = "#999999"
BLUE_SYSTEM = "#888888"
FONT_FAMILY = "微软雅黑"

EMOJI_LIST = [
    "😀", "😂", "🤣", "😅", "😊", "😍",
    "🤔", "😐", "😢", "😠", "😨", "🤯",
    "👍", "👎", "👏", "🙏", "💪", "🤝",
    "❤️", "🔥", "⭐", "🎉", "✨", "💡",
    "🍔", "🍕", "☕", "🍺", "🎂", "🌈",
    "🚗", "✈️", "🏠", "🌍", "⏰", "📅",
    "📎", "🔒", "💻", "📱", "🎵", "📸",
    "🐱", "🐶", "🎮", "⚽", "🎬", "🎯",
    "✅", "❌", "⚠️", "🔍", "📝", "💬",
]


def file_icon(filename):
    ext = os.path.splitext(filename)[1].lower()
    return {
        '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', '.gif': '🖼️', '.bmp': '🖼️', '.webp': '🖼️', '.svg': '🖼️',
        '.mp4': '🎬', '.avi': '🎬', '.mov': '🎬', '.mkv': '🎬', '.wmv': '🎬',
        '.mp3': '🎵', '.wav': '🎵', '.flac': '🎵', '.aac': '🎵', '.ogg': '🎵',
        '.pdf': '📕',
        '.zip': '📦', '.rar': '📦', '.7z': '📦', '.tar': '📦', '.gz': '📦',
        '.doc': '📝', '.docx': '📝', '.txt': '📝', '.md': '📝',
        '.xls': '📊', '.xlsx': '📊', '.csv': '📊',
        '.ppt': '📽️', '.pptx': '📽️',
        '.py': '💻', '.js': '💻', '.ts': '💻', '.html': '💻', '.css': '💻', '.java': '💻', '.cpp': '💻', '.c': '💻',
        '.exe': '⚙️', '.msi': '⚙️', '.dmg': '⚙️', '.apk': '⚙️',
    }.get(ext, '📄')


def format_size(fsize):
    if fsize < 1024:
        return f"{fsize} B"
    elif fsize < 1024 * 1024:
        return f"{fsize / 1024:.1f} KB"
    else:
        return f"{fsize / 1024 / 1024:.1f} MB"


def is_image(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')


def create_thumbnail(filepath, max_size=(240, 240)):
    try:
        img = Image.open(filepath)
        img.thumbnail(max_size, Image.LANCZOS)
        os.makedirs("downloads/.thumbnails", exist_ok=True)
        thumb_name = os.path.basename(filepath) + ".thumb.png"
        thumb_path = os.path.join("downloads", ".thumbnails", thumb_name)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGBA')
            img.save(thumb_path, 'PNG')
        else:
            img.save(thumb_path, 'JPEG', quality=85)
        return thumb_path
    except Exception:
        return None


def format_time(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.astimezone().strftime("%H:%M")
    except Exception:
        return ""


def wrap_text(text, max_width, font):
    lines = []
    current = ""
    for char in text:
        if font.measure(current + char) <= max_width:
            current += char
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines if lines else [""]


def render_text_bubble(parent, sender, content, timestamp_str, my_username, bubble_font, time_font):
    """在 parent (bubble_frame) 中渲染一条文字气泡"""
    is_me = (sender == my_username)
    is_system = (sender == "[系统]")

    if is_system:
        lbl = tk.Label(parent, text=content, font=time_font,
                      fg=BLUE_SYSTEM, bg=BG_COLOR)
        lbl.pack(pady=2)
        return

    max_text_width = 380
    lines = wrap_text(content, max_text_width, bubble_font)
    bubble_bg = GREEN_BUBBLE if is_me else WHITE

    outer = tk.Frame(parent, bg=BG_COLOR)
    if is_me:
        outer.pack(anchor="e", pady=1, padx=(40, 6))
    else:
        outer.pack(anchor="w", pady=1, padx=(6, 40))

    if not is_me:
        tk.Label(outer, text=sender, font=time_font,
                fg=GRAY, bg=BG_COLOR, anchor="w").pack(anchor="w", padx=(4, 0))

    inner = tk.Frame(outer, bg=bubble_bg)
    inner.pack(anchor="e" if is_me else "w")

    for line in lines:
        tk.Label(inner, text=line, font=bubble_font,
                bg=bubble_bg, fg=BLACK, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(1, 0))

    ts = format_time(timestamp_str)
    ts_lbl = tk.Label(outer, text=ts, font=time_font, fg=GRAY, bg=BG_COLOR)
    if is_me:
        ts_lbl.pack(anchor="e", padx=(0, 4))
    else:
        ts_lbl.pack(anchor="w", padx=(4, 0))


def render_file_card(parent, sender, filename, fsize, file_id, is_sender, my_username,
                     bubble_font, time_font, on_download):
    """渲染文件卡片气泡，返回 (btn, progress_var) 或 (None, None)"""
    is_me = (sender == my_username)
    bubble_bg = GREEN_BUBBLE if is_me else WHITE
    icon = file_icon(filename)
    size_str = format_size(fsize)

    outer = tk.Frame(parent, bg=BG_COLOR)
    if is_me:
        outer.pack(anchor="e", pady=2, padx=(40, 8))
    else:
        outer.pack(anchor="w", pady=2, padx=(8, 40))

    if not is_me:
        tk.Label(outer, text=sender, font=time_font,
                fg=GRAY, bg=BG_COLOR, anchor="w").pack(anchor="w", padx=(4, 0))

    inner = tk.Frame(outer, bg=bubble_bg, padx=12, pady=8)
    inner.pack()

    info_row = tk.Frame(inner, bg=bubble_bg)
    info_row.pack(fill="x")

    tk.Label(info_row, text=icon, font=(FONT_FAMILY, 20),
            bg=bubble_bg).pack(side="left", padx=(0, 8))

    text_col = tk.Frame(info_row, bg=bubble_bg)
    text_col.pack(side="left", fill="x", expand=True)

    tk.Label(text_col, text=filename, font=bubble_font,
            bg=bubble_bg, fg=BLACK, anchor="w",
            wraplength=260).pack(anchor="w")
    tk.Label(text_col, text=size_str, font=time_font,
            bg=bubble_bg, fg=GRAY, anchor="w").pack(anchor="w", pady=(2, 0))

    btn = None
    progress_var = None
    if not is_sender:
        progress_var = tk.StringVar(value="⬇ 下载")
        btn_frame = tk.Frame(inner, bg=bubble_bg)
        btn_frame.pack(fill="x", pady=(8, 0))
        btn = tk.Button(btn_frame, textvariable=progress_var,
                       font=(FONT_FAMILY, 9), relief=tk.FLAT, cursor="hand2",
                       bg="#07C160", fg=WHITE, activebackground="#06AD56",
                       activeforeground=WHITE, padx=14, pady=2)
        btn.config(command=lambda pv=progress_var, b=btn, fid=file_id, fn=filename:
                   on_download(fid, fn, pv, b))
        btn.pack()

    return btn, progress_var


def render_image_bubble(parent, sender, image_path, is_sender, my_username,
                        bubble_font, time_font, on_view, photo_refs):
    """渲染图片缩略图内联显示，返回 True 成功 / False 失败（回退文件卡片）"""
    thumb_path = create_thumbnail(image_path)
    if not thumb_path:
        return False

    is_me = (sender == my_username)
    bubble_bg = GREEN_BUBBLE if is_me else WHITE

    outer = tk.Frame(parent, bg=BG_COLOR)
    if is_me:
        outer.pack(anchor="e", pady=2, padx=(40, 8))
    else:
        outer.pack(anchor="w", pady=2, padx=(8, 40))

    if not is_me:
        tk.Label(outer, text=sender, font=time_font,
                fg=GRAY, bg=BG_COLOR, anchor="w").pack(anchor="w", padx=(4, 0))

    inner = tk.Frame(outer, bg=bubble_bg, padx=3, pady=3)
    inner.pack()

    try:
        pil_img = Image.open(thumb_path)
        photo = ImageTk.PhotoImage(pil_img)
    except Exception:
        return False

    photo_refs.append(photo)
    lbl = tk.Label(inner, image=photo, bg=bubble_bg, cursor="hand2")
    lbl.image = photo
    lbl.pack()
    lbl.bind("<Button-1>", lambda e, p=image_path: on_view(p))
    return True
