"""
图片查看器：大图弹窗 + 自动下载
"""

import os
import socket
import threading
import tkinter as tk
from PIL import Image, ImageTk

from common.protocol import DEFAULT_HOST, FILE_PORT, FILE_CHUNK, ENCODING
from client.ui.widgets import BLACK, FONT_FAMILY


def show_image_viewer(parent, image_path):
    """弹出大图查看窗口"""
    try:
        pil_img = Image.open(image_path)
    except Exception:
        return

    viewer = tk.Toplevel(parent)
    fname = os.path.basename(image_path)
    viewer.title(f"图片查看 - {fname}")
    viewer.configure(bg=BLACK)

    sw = viewer.winfo_screenwidth()
    sh = viewer.winfo_screenheight()
    max_w, max_h = int(sw * 0.8), int(sh * 0.8)

    if pil_img.width > max_w or pil_img.height > max_h:
        pil_img.thumbnail((max_w, max_h), Image.LANCZOS)

    photo = ImageTk.PhotoImage(pil_img)
    lbl = tk.Label(viewer, image=photo, bg=BLACK, cursor="hand2")
    lbl.image = photo
    lbl.pack()

    lbl.bind("<Button-1>", lambda e: viewer.destroy())
    viewer.bind("<Escape>", lambda e: viewer.destroy())

    viewer.update_idletasks()
    w, h = viewer.winfo_width(), viewer.winfo_height()
    x = (sw - w) // 2
    y = (sh - h) // 2
    viewer.geometry(f"+{x}+{y}")
    viewer.focus_set()


def auto_download_image(file_id, filename, sender, on_done, on_error):
    """后台线程自动下载图片，完成后回调 on_done(sender, save_path)"""
    def run():
        try:
            fs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            fs.settimeout(30)
            fs.connect((DEFAULT_HOST, FILE_PORT))
            fs.sendall((file_id + "\n").encode(ENCODING))

            os.makedirs("downloads", exist_ok=True)
            save_path = os.path.join("downloads", filename)
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(save_path):
                save_path = os.path.join("downloads", f"{base} ({counter}){ext}")
                counter += 1

            with open(save_path, "wb") as f:
                while True:
                    chunk = fs.recv(FILE_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
            fs.close()
            on_done(sender, save_path)
        except Exception as e:
            on_error(str(e))
    threading.Thread(target=run, daemon=True).start()
