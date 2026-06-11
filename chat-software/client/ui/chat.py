"""
聊天主窗口
"""

import os
import socket
import threading
import tkinter as tk
from tkinter import ttk, filedialog
import tkinter.font as tkfont

from common.protocol import (
    DEFAULT_HOST, FILE_PORT, FILE_CHUNK, ENCODING,
    TYPE_BROADCAST, TYPE_PRIVATE, TYPE_GET_USERS, TYPE_RESPONSE, TYPE_SYSTEM,
    TYPE_GET_HISTORY, TYPE_HISTORY,
    TYPE_CREATE_GROUP, TYPE_JOIN_GROUP, TYPE_ADD_MEMBER, TYPE_LEAVE_GROUP,
    TYPE_DELETE_GROUP, TYPE_GROUP_USERS, TYPE_GROUP_MSG,
    TYPE_FILE_SEND, TYPE_FILE_NOTIFY, TYPE_FILE_DOWNLOAD,
    TYPE_SEARCH_USERS, TYPE_ADD_CONTACT,
    STATUS_OK,
)
from client.network import NetworkClient
from client.ui.widgets import (
    BG_COLOR, LEFT_BG, WHITE, GREEN_BUBBLE, BLACK, GRAY, FONT_FAMILY,
    is_image, format_size, file_icon,
    render_text_bubble, render_file_card, render_image_bubble,
)
from client.ui.dialogs import (
    show_search_users_dialog, show_add_member_dialog,
    show_create_group_dialog, show_group_members, show_emoji_panel,
)
from client.ui.viewer import show_image_viewer, auto_download_image


class ChatWindow:
    def __init__(self, nc, username, public_history=None, conversations=None, groups=None, contacts=None):
        self.nc = nc  # NetworkClient
        self.username = username
        self.running = True
        self.current_chat = "public"
        self.online_users = set()
        self._conv_partners = list(conversations) if conversations else []
        self._contacts = list(contacts) if contacts else []
        for c in self._contacts:
            if c not in self._conv_partners:
                self._conv_partners.append(c)
        self._groups = groups or []
        self._pending_upload = None
        self._photo_refs = []  # 防 GC

        self.root = tk.Tk()
        self.bubble_font = tkfont.Font(family=FONT_FAMILY, size=10)
        self.time_font = tkfont.Font(family=FONT_FAMILY, size=8)
        self.root.title(f"局域网聊天 - {username}")
        self.root.geometry("800x550")
        self.root.configure(bg=BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL,
                                     sashrelief=tk.RAISED, sashwidth=1, bg=BG_COLOR)
        self.paned.pack(fill=tk.BOTH, expand=True)

        self._build_left_panel()
        self._build_right_panel()

        self._rebuild_conv_list()
        self.conv_tree.selection_set("public")
        self._on_tree_select()

        if public_history:
            self._render_history(public_history)

        self._setup_handlers()
        self.nc.start_receive()

        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

        self.refresh_users()

    # ========================
    #  UI 构建
    # ========================
    def _build_left_panel(self):
        self.left_frame = tk.Frame(self.paned, width=200, bg=LEFT_BG)
        self.paned.add(self.left_frame, minsize=150)
        self.left_frame.pack_propagate(False)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._filter_conversations())
        self.search_entry = tk.Entry(self.left_frame, textvariable=self.search_var,
                                      font=(FONT_FAMILY, 9), fg=GRAY)
        self.search_entry.insert(0, "搜索")
        self.search_entry.bind("<FocusIn>", lambda e: self._on_search_focus_in())
        self.search_entry.bind("<FocusOut>", lambda e: self._on_search_focus_out())
        self.search_entry.pack(fill="x", padx=8, pady=(8, 4))

        self.conv_tree = ttk.Treeview(self.left_frame, show="tree",
                                       selectmode="browse", height=20)
        self.conv_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        self.conv_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.conv_tree.bind("<Button-3>", self._on_tree_right_click)
        self._tree_menu = tk.Menu(self.left_frame, tearoff=0)

        self.tree_root = self.conv_tree.insert("", "end", text="", open=True, iid="root")
        self.tree_public = self.conv_tree.insert("root", "end", iid="public", text="★ 公聊大厅")
        self.tree_groups = self.conv_tree.insert("root", "end", iid="groups", text="▼ 群聊", open=True)
        self._group_tree_ids = {}
        self.tree_contacts = self.conv_tree.insert("root", "end", iid="contacts", text="▼ 联系人", open=True)
        self._contact_tree_ids = []

        btn_frame = tk.Frame(self.left_frame, bg=LEFT_BG)
        btn_frame.pack(fill="x", padx=4, pady=(0, 4))
        tk.Button(btn_frame, text="+ 创建群", font=(FONT_FAMILY, 9),
                 bg=LEFT_BG, relief=tk.GROOVE, cursor="hand2",
                 command=self._create_group).pack(fill="x")
        tk.Button(btn_frame, text="+ 添加好友", font=(FONT_FAMILY, 9),
                 bg=LEFT_BG, relief=tk.GROOVE, cursor="hand2",
                 command=self._open_search_dialog).pack(fill="x", pady=(2, 0))

    def _build_right_panel(self):
        self.right_frame = tk.Frame(self.paned, bg=BG_COLOR)
        self.paned.add(self.right_frame, minsize=400)

        self.title_bar = tk.Frame(self.right_frame, height=44, bg=BG_COLOR)
        self.title_bar.pack(fill="x", padx=12, pady=(8, 0))
        self.title_bar.pack_propagate(False)
        self.title_label = tk.Label(self.title_bar, text="公聊大厅",
                                     font=(FONT_FAMILY, 12, "bold"), bg=BG_COLOR, fg=BLACK)
        self.title_label.pack(side="left", pady=6)

        sep = tk.Frame(self.right_frame, height=1, bg="#E0E0E0")
        sep.pack(fill="x", padx=12)

        self.chat_container = tk.Frame(self.right_frame, bg=BG_COLOR)
        self.chat_container.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        self.chat_canvas = tk.Canvas(self.chat_container, bg=BG_COLOR, highlightthickness=0)
        self.chat_scrollbar = tk.Scrollbar(self.chat_container, orient=tk.VERTICAL,
                                            command=self.chat_canvas.yview)
        self.chat_canvas.configure(yscrollcommand=self.chat_scrollbar.set)
        self.chat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.bubble_frame = tk.Frame(self.chat_canvas, bg=BG_COLOR)
        self.bubble_frame.bind("<Configure>",
            lambda e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all")))
        self.canvas_window = self.chat_canvas.create_window((0, 0), window=self.bubble_frame,
                                                             anchor="nw", tags="bubble_frame")
        self.chat_canvas.bind("<Configure>", self._on_canvas_resize)
        self.chat_canvas.bind("<Enter>", lambda e: self._bind_mousewheel())
        self.chat_canvas.bind("<Leave>", lambda e: self._unbind_mousewheel())

        self.input_frame = tk.Frame(self.right_frame, bg=BG_COLOR, height=50)
        self.input_frame.pack(fill="x", padx=12, pady=(4, 10))
        self.input_frame.pack_propagate(False)

        self.entry_msg = tk.Entry(self.input_frame, font=(FONT_FAMILY, 10),
                                   bg=WHITE, relief=tk.FLAT)
        self.entry_msg.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry_msg.bind("<Return>", self.send_message)

        self.send_btn = tk.Button(self.input_frame, text="发送", width=8,
                                   command=self.send_message, bg="#2DC100", fg=WHITE,
                                   font=(FONT_FAMILY, 9), relief=tk.FLAT, cursor="hand2")
        self.send_btn.pack(side=tk.RIGHT, padx=(6, 0), ipady=2)

        self.emoji_btn = tk.Button(self.input_frame, text="😀", width=4,
                                    command=lambda: show_emoji_panel(self.root, self.emoji_btn, self.entry_msg),
                                    bg=BG_COLOR, fg=BLACK,
                                    font=(FONT_FAMILY, 12), relief=tk.FLAT, cursor="hand2")
        self.emoji_btn.pack(side=tk.RIGHT, ipady=2)

        self.attach_btn = tk.Button(self.input_frame, text="📎", width=4,
                                     command=self._send_file, bg=BG_COLOR, fg=BLACK,
                                     font=(FONT_FAMILY, 12), relief=tk.FLAT, cursor="hand2")
        self.attach_btn.pack(side=tk.RIGHT, ipady=2)

    # ========================
    #  消息接收路由
    # ========================
    def _setup_handlers(self):
        self.nc.set_handler(TYPE_BROADCAST, self._on_broadcast)
        self.nc.set_handler(TYPE_PRIVATE, self._on_private)
        self.nc.set_handler(TYPE_GET_USERS, self._on_get_users)
        self.nc.set_handler(TYPE_RESPONSE, self._on_response)
        self.nc.set_handler(TYPE_HISTORY, self._on_history)
        self.nc.set_handler(TYPE_GROUP_USERS, self._on_group_users)
        self.nc.set_handler(TYPE_GROUP_MSG, self._on_group_msg)
        self.nc.set_handler(TYPE_FILE_NOTIFY, self._on_file_notify)
        self.nc.set_handler(TYPE_SEARCH_USERS, self._on_search_users)
        self.nc.set_handler("system_disconnect", self._on_disconnect)
        self.nc.set_handler("system_error", self._on_disconnect)

    # ========================
    #  消息处理
    # ========================
    def _on_broadcast(self, msg):
        sender = msg.get("sender", "未知")
        content = msg.get("content", "")
        ts = msg.get("timestamp", "")
        if sender == "[系统]":
            self._add_bubble(sender, content, ts)
        elif self.current_chat == "public":
            self._add_bubble(sender, content, ts)

    def _on_private(self, msg):
        sender = msg.get("sender", "未知")
        content = msg.get("content", "")
        ts = msg.get("timestamp", "")
        target = msg.get("target", "")
        partner = target if sender == self.username else sender
        if self.current_chat == partner or self.current_chat == sender:
            self._add_bubble(sender, content, ts)
        if partner != self.username and partner not in self._conv_partners:
            self._conv_partners.append(partner)
            self._rebuild_conv_list()

    def _on_get_users(self, msg):
        def upd():
            self.online_users = set(msg.get("users", []))
        self.root.after(0, upd)

    def _on_response(self, msg):
        # 群创建/加入/被邀请
        group_data = msg.get("group")
        if group_data:
            notify_msg = msg.get("message", "")
            exist = [g for g in self._groups if g['id'] == group_data['id']]
            if not exist:
                self._groups.append(group_data)
                if notify_msg:
                    self._add_bubble("[系统]", notify_msg, "")
            self._rebuild_conv_list()
            self.root.after(100, lambda gid=group_data['id']: self._switch_to(f"group:{gid}"))
        # 文件发送响应
        file_id = msg.get("file_id")
        if file_id and self._pending_upload:
            self._do_file_upload(file_id, self._pending_upload)
            self._pending_upload = None
        # 添加好友响应
        contact = msg.get("contact")
        if contact and contact not in self._conv_partners:
            self._conv_partners.append(contact)
            self._contacts.append(contact)
            self._rebuild_conv_list()
            m = msg.get("message", "")
            if m:
                self._add_bubble("[系统]", m, "")

    def _on_history(self, msg):
        target = msg.get("target", "")
        if target == self.current_chat:
            self.root.after(0, lambda: self._render_history(msg.get("messages", [])))

    def _on_group_users(self, msg):
        users = msg.get("users", [])
        gid = msg.get("group_id")
        self.root.after(0, lambda: show_group_members(self.root, gid, users))

    def _on_group_msg(self, msg):
        sender = msg.get("sender", "未知")
        content = msg.get("content", "")
        ts = msg.get("timestamp", "")
        gid = msg.get("group_id")
        if self.current_chat == f"group:{gid}":
            self._add_bubble(sender, content, ts)

    def _on_file_notify(self, msg):
        filename = msg.get("filename", "")
        fsize = msg.get("size", 0)
        file_id = msg.get("file_id", "")
        sender = msg.get("sender", "")
        if is_image(filename):
            auto_download_image(
                file_id, filename, sender,
                on_done=lambda snd, path: self.root.after(0, lambda: self._show_image_bubble(snd, path)),
                on_error=lambda e: self._add_bubble("[系统]", f"图片加载失败: {e}", ""),
            )
        else:
            self.root.after(0, lambda: self._show_file_card(sender, filename, fsize, file_id, False))

    def _on_search_users(self, msg):
        cb = getattr(self, '_search_result_cb', None)
        if cb:
            self.root.after(0, lambda: cb(msg.get("users", [])))

    def _on_disconnect(self, msg):
        self._add_bubble("[系统]", "与服务器断开连接", "")

    # ========================
    #  气泡渲染（线程安全）
    # ========================
    def _add_bubble(self, sender, content, ts):
        def _add():
            render_text_bubble(self.bubble_frame, sender, content, ts,
                              self.username, self.bubble_font, self.time_font)
            self._scroll_to_bottom()
        self.root.after(0, _add)

    def _show_file_card(self, sender, filename, fsize, file_id, is_sender):
        render_file_card(self.bubble_frame, sender, filename, fsize, file_id, is_sender,
                        self.username, self.bubble_font, self.time_font, self._download_file)
        self._scroll_to_bottom()

    def _show_image_bubble(self, sender, image_path):
        ok = render_image_bubble(self.bubble_frame, sender, image_path,
                                 sender == self.username, self.username,
                                 self.bubble_font, self.time_font,
                                 lambda p: show_image_viewer(self.root, p),
                                 self._photo_refs)
        if not ok:
            fname = os.path.basename(image_path)
            fsize = os.path.getsize(image_path) if os.path.exists(image_path) else 0
            self._show_file_card(sender, fname, fsize, "", sender == self.username)
        self._scroll_to_bottom()

    # ========================
    #  下载
    # ========================
    def _download_file(self, file_id, filename, progress_var, btn):
        def run():
            self.root.after(0, lambda: progress_var.set("下载中..."))
            self.root.after(0, lambda: btn.config(state=tk.DISABLED))
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
                self.root.after(0, lambda: progress_var.set("✓ 已下载"))
                self._add_bubble("[系统]", f"文件已保存: {save_path}", "")
            except Exception as e:
                self.root.after(0, lambda: progress_var.set("⬇ 重试"))
                self.root.after(0, lambda: btn.config(state=tk.NORMAL))
                self._add_bubble("[系统]", f"下载失败: {e}", "")
        threading.Thread(target=run, daemon=True).start()

    # ========================
    #  文件发送
    # ========================
    def _send_file(self):
        filepath = filedialog.askopenfilename(parent=self.root, title="选择文件")
        if not filepath:
            return
        filename = os.path.basename(filepath)
        fsize = os.path.getsize(filepath)

        if is_image(filename):
            self._show_image_bubble(self.username, filepath)

        receiver = self.current_chat if not self.current_chat.startswith("group:") and self.current_chat != "public" else self.username
        try:
            self.nc.send(TYPE_FILE_SEND, receiver=receiver, filename=filename, size=fsize)
        except Exception as e:
            self._add_bubble("[系统]", f"发送文件失败: {e}", "")
            return
        self._pending_upload = {"filepath": filepath, "filename": filename, "fsize": fsize, "receiver": receiver}

    def _do_file_upload(self, file_id, info):
        def upload():
            try:
                fs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                fs.settimeout(30)
                fs.connect((DEFAULT_HOST, FILE_PORT))
                fs.sendall((file_id + "\n").encode(ENCODING))
                with open(info["filepath"], "rb") as f:
                    while True:
                        chunk = f.read(FILE_CHUNK)
                        if not chunk:
                            break
                        fs.sendall(chunk)
                fs.close()
                if not is_image(info["filename"]):
                    self.root.after(0, lambda: self._show_file_card(
                        self.username, info["filename"], info["fsize"], file_id, True))
            except Exception as e:
                self._add_bubble("[系统]", f"上传文件失败: {e}", "")
        threading.Thread(target=upload, daemon=True).start()

    # ========================
    #  发送消息
    # ========================
    def send_message(self, event=None):
        content = self.entry_msg.get().strip()
        if not content:
            return
        self.entry_msg.delete(0, "end")

        if content.startswith("@"):
            parts = content.split(" ", 1)
            if len(parts) >= 2:
                target = parts[0][1:]
                msg_content = parts[1]
                try:
                    self.nc.send(TYPE_PRIVATE, target=target, content=msg_content, timestamp="")
                except Exception as e:
                    self._add_bubble("[系统]", f"发送失败: {e}", "")
                    return
                if target not in self._conv_partners:
                    self._conv_partners.append(target)
                    self._rebuild_conv_list()
                return
            else:
                self._add_bubble("[系统]", "私聊格式: @用户名 消息内容", "")
                return

        if self.current_chat.startswith("group:"):
            gid = int(self.current_chat.split(":")[1])
            try:
                self.nc.send(TYPE_GROUP_MSG, group_id=gid, content=content, timestamp="")
            except Exception as e:
                self._add_bubble("[系统]", f"发送失败: {e}", "")
            return

        try:
            self.nc.send(TYPE_BROADCAST, content=content, timestamp="")
        except Exception as e:
            self._add_bubble("[系统]", f"发送失败: {e}", "")
            return
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        self._add_bubble(self.username, content, ts)

    # ========================
    #  会话列表
    # ========================
    def _rebuild_conv_list(self):
        def _rebuild():
            for iid in self._contact_tree_ids:
                self.conv_tree.delete(iid)
            self._contact_tree_ids.clear()
            for iid in self._group_tree_ids.values():
                self.conv_tree.delete(iid)
            self._group_tree_ids.clear()

            for g in getattr(self, '_groups', []):
                iid = f"group:{g['id']}"
                self._group_tree_ids[g['id']] = self.conv_tree.insert(
                    self.tree_groups, "end", iid=iid, text=f"  {g['name']}",
                )
            for p in self._conv_partners:
                online = p in self.online_users
                prefix = "● " if online else "○ "
                iid = f"contact:{p}"
                self.conv_tree.insert(self.tree_contacts, "end", iid=iid, text=f"  {prefix}{p}")
                self._contact_tree_ids.append(iid)
        self.root.after(0, _rebuild)

    def _render_history(self, messages):
        self._clear_bubbles()
        for m in messages:
            render_text_bubble(self.bubble_frame,
                m.get("sender", "未知"), m.get("content", ""), m.get("timestamp", ""),
                self.username, self.bubble_font, self.time_font)
        self._scroll_to_bottom()

    def _clear_bubbles(self):
        for w in self.bubble_frame.winfo_children():
            w.destroy()

    def _on_tree_select(self, event=None):
        sel = self.conv_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "public":
            self.current_chat = "public"
            self.title_label.config(text="公聊大厅")
            self.nc.send(TYPE_GET_HISTORY, target="public")
        elif iid.startswith("group:"):
            gid = int(iid.split(":")[1])
            self.current_chat = f"group:{gid}"
            for g in getattr(self, '_groups', []):
                if g['id'] == gid:
                    self.title_label.config(text=g['name'])
                    break
            self.nc.send(TYPE_GET_HISTORY, target=self.current_chat)
        elif iid.startswith("contact:"):
            partner = iid.split(":", 1)[1]
            self.current_chat = partner
            self.title_label.config(text=partner)
            self.nc.send(TYPE_GET_HISTORY, target=partner)

    def _on_tree_right_click(self, event):
        item = self.conv_tree.identify_row(event.y)
        if not item or item in ("root", "public", "groups", "contacts"):
            return
        self.conv_tree.selection_set(item)
        self._tree_menu.delete(0, tk.END)

        if item.startswith("group:"):
            gid = int(item.split(":")[1])
            grp = None
            for g in self._groups:
                if g['id'] == gid:
                    grp = g
                    break
            if not grp:
                return
            self._tree_menu.add_command(label="查看成员", command=lambda: self.nc.send(TYPE_GROUP_USERS, group_id=gid))
            self._tree_menu.add_command(label="添加成员", command=lambda: self._do_add_member(gid))
            self._tree_menu.add_command(label="退出群", command=lambda: self._do_leave_group(gid))
            if grp.get("created_by") == self.username:
                self._tree_menu.add_command(label="解散群", command=lambda: self._do_delete_group(gid))
        elif item.startswith("contact:"):
            self._tree_menu.add_command(label="发起私聊", command=lambda: self._on_tree_select())
        self._tree_menu.post(event.x_root, event.y_root)

    def _do_add_member(self, gid):
        username = show_add_member_dialog(self.root)
        if username and username.strip():
            try:
                self.nc.send(TYPE_ADD_MEMBER, group_id=gid, target=username.strip())
            except Exception as e:
                self._add_bubble("[系统]", f"添加成员失败: {e}", "")

    def _do_leave_group(self, gid):
        try:
            self.nc.send(TYPE_LEAVE_GROUP, group_id=gid)
        except Exception:
            pass
        self._groups = [g for g in self._groups if g['id'] != gid]
        self._rebuild_conv_list()

    def _do_delete_group(self, gid):
        try:
            self.nc.send(TYPE_DELETE_GROUP, group_id=gid)
        except Exception:
            pass
        self._groups = [g for g in self._groups if g['id'] != gid]
        self._rebuild_conv_list()

    def _create_group(self):
        name = show_create_group_dialog(self.root)
        if name and name.strip():
            try:
                self.nc.send(TYPE_CREATE_GROUP, name=name.strip())
            except Exception as e:
                self._add_bubble("[系统]", f"创建群失败: {e}", "")

    def _open_search_dialog(self):
        self._search_result_cb = show_search_users_dialog(self.root, lambda data: self.nc.send_raw(data))

    def _switch_to(self, chat_key):
        self.current_chat = chat_key
        try:
            self.nc.send(TYPE_GET_HISTORY, target=chat_key)
        except Exception:
            pass

    def _filter_conversations(self):
        query = self.search_var.get().strip()
        if query == "搜索" or not query:
            self._rebuild_conv_list()
            return
        def _filter():
            for iid in self._contact_tree_ids:
                self.conv_tree.delete(iid)
            self._contact_tree_ids.clear()
            for iid in self._group_tree_ids.values():
                self.conv_tree.delete(iid)
            self._group_tree_ids.clear()
            for g in self._groups:
                if query.lower() in g['name'].lower():
                    iid = f"group:{g['id']}"
                    self._group_tree_ids[g['id']] = self.conv_tree.insert(
                        self.tree_groups, "end", iid=iid, text=f"  {g['name']}",
                    )
            for p in self._conv_partners:
                if query.lower() in p.lower():
                    iid = f"contact:{p}"
                    self.conv_tree.insert(self.tree_contacts, "end", iid=iid, text=f"  {p}")
                    self._contact_tree_ids.append(iid)
        self.root.after(0, _filter)

    def _on_search_focus_in(self):
        if self.search_var.get() == "搜索":
            self.search_entry.delete(0, tk.END)
            self.search_entry.config(fg=BLACK)

    def _on_search_focus_out(self):
        if not self.search_var.get().strip():
            self.search_entry.insert(0, "搜索")
            self.search_entry.config(fg=GRAY)

    # ========================
    #  Canvas / 滚动
    # ========================
    def _on_canvas_resize(self, event):
        self.chat_canvas.itemconfig(self.canvas_window, width=event.width)

    def _bind_mousewheel(self):
        self.chat_canvas.bind_all("<MouseWheel>",
            lambda e: self.chat_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def _unbind_mousewheel(self):
        self.chat_canvas.unbind_all("<MouseWheel>")

    def _scroll_to_bottom(self):
        self.chat_canvas.after(50, lambda: self.chat_canvas.yview_moveto(1.0))

    # ========================
    #  工具
    # ========================
    def refresh_users(self):
        try:
            self.nc.send(TYPE_GET_USERS)
        except Exception:
            pass
        if self.running:
            self.root.after(5000, self.refresh_users)

    def on_close(self):
        self.running = False
        self.nc.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
