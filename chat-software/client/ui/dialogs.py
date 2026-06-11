"""
弹窗组件：搜索好友、添加成员、创建群、emoji面板
"""

import tkinter as tk
from tkinter import simpledialog, messagebox

from common.protocol import (
    TYPE_SEARCH_USERS, TYPE_ADD_CONTACT,
    make_message,
)
from client.ui.widgets import BG_COLOR, WHITE, FONT_FAMILY, EMOJI_LIST, BLACK, GRAY


def show_search_users_dialog(parent, on_send):
    """弹出搜索好友对话框。on_send(msg_dict) 发送消息到服务器"""
    dialog = tk.Toplevel(parent)
    dialog.title("添加好友")
    dialog.geometry("300x350")
    dialog.resizable(False, False)
    dialog.configure(bg=BG_COLOR)

    frm_top = tk.Frame(dialog, bg=BG_COLOR)
    frm_top.pack(fill="x", padx=10, pady=(10, 4))
    entry = tk.Entry(frm_top, font=(FONT_FAMILY, 10))
    entry.pack(side="left", fill="x", expand=True, ipady=2)

    list_frame = tk.Frame(dialog, bg=WHITE)
    list_frame.pack(fill="both", expand=True, padx=10, pady=4)
    listbox = tk.Listbox(list_frame, font=(FONT_FAMILY, 10), bg=WHITE,
                        selectmode=tk.SINGLE, relief=tk.FLAT)
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar = tk.Scrollbar(list_frame, command=listbox.yview)
    scrollbar.pack(side="right", fill="y")
    listbox.config(yscrollcommand=scrollbar.set)

    result_users = []

    def do_search(*args):
        query = entry.get().strip()
        if not query:
            return
        on_send(make_message(TYPE_SEARCH_USERS, query=query).encode())

    entry.bind("<Return>", do_search)

    def on_result(users):
        result_users.clear()
        result_users.extend(users)
        listbox.delete(0, tk.END)
        for u in users:
            listbox.insert(tk.END, f"  {u}")
        if not users:
            listbox.insert(tk.END, "  无匹配用户")

    def add_selected():
        sel = listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(result_users):
            data = make_message(TYPE_ADD_CONTACT, username=result_users[idx]).encode()
            on_send(data)

    btn_frame = tk.Frame(dialog, bg=BG_COLOR)
    btn_frame.pack(fill="x", padx=10, pady=(4, 10))
    tk.Button(btn_frame, text="搜索", command=do_search,
             font=(FONT_FAMILY, 9), bg="#07C160", fg=WHITE,
             relief=tk.FLAT, padx=12).pack(side="left")
    tk.Button(btn_frame, text="添加好友", command=add_selected,
             font=(FONT_FAMILY, 9), bg=WHITE, relief=tk.GROOVE,
             padx=12).pack(side="right")

    entry.focus_set()
    dialog.update_idletasks()
    w, h = dialog.winfo_width(), dialog.winfo_height()
    x = (dialog.winfo_screenwidth() - w) // 2
    y = (dialog.winfo_screenheight() - h) // 2
    dialog.geometry(f"+{x}+{y}")
    return on_result


def show_add_member_dialog(parent):
    """弹出添加群成员输入框，返回用户名或 None"""
    return simpledialog.askstring("添加成员", "请输入要添加的用户名:", parent=parent)


def show_create_group_dialog(parent):
    """弹出创建群聊输入框，返回群名或 None"""
    return simpledialog.askstring("创建群聊", "请输入群名:", parent=parent)


def show_group_members(parent, gid, members):
    """弹出群成员列表"""
    messagebox.showinfo(f"群成员 (id={gid})", "\n".join(members))


def show_emoji_panel(parent, emoji_btn, entry_msg):
    """弹出 emoji 选择面板"""
    panel = tk.Toplevel(parent)
    panel.title("")
    panel.overrideredirect(True)
    panel.attributes("-topmost", True)
    panel.configure(bg=WHITE)

    x = emoji_btn.winfo_rootx()
    y = emoji_btn.winfo_rooty() - 200
    panel.geometry(f"240x300+{x}+{y}")

    cols = 6
    for i, em in enumerate(EMOJI_LIST):
        row = i // cols
        col = i % cols
        btn = tk.Button(panel, text=em, font=(FONT_FAMILY, 12),
                       bg=WHITE, relief=tk.FLAT, cursor="hand2",
                       command=lambda e=em: _insert_and_close(e, panel, entry_msg))
        btn.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
        for c in range(cols):
            panel.grid_columnconfigure(c, weight=1)

    def on_focus_out(event):
        if event.widget == panel:
            panel.destroy()
    panel.bind("<FocusOut>", on_focus_out)
    panel.focus_set()


def _insert_and_close(emoji, panel, entry):
    pos = entry.index(tk.INSERT)
    entry.insert(pos, emoji)
    panel.destroy()
    entry.focus_set()
