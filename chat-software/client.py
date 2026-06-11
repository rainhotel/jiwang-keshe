"""
聊天客户端：tkinter GUI
功能：连接服务器、注册/登录、公聊、私聊、在线用户列表
"""

import json
import socket
import threading
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from datetime import datetime, timezone
from tkinter import messagebox, simpledialog

from common import (
    DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE, ENCODING,
    TYPE_REGISTER, TYPE_LOGIN, TYPE_BROADCAST, TYPE_PRIVATE,
    TYPE_GET_USERS, TYPE_SYSTEM, TYPE_RESPONSE,
    TYPE_GET_HISTORY, TYPE_HISTORY,
    TYPE_CREATE_GROUP, TYPE_JOIN_GROUP, TYPE_LEAVE_GROUP,
    TYPE_DELETE_GROUP, TYPE_GROUP_USERS, TYPE_GROUP_MSG,
    STATUS_OK, STATUS_ERROR,
    make_message, parse_message, conversation_key, group_key,
)

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


# ============================
#  登录/注册窗口
# ============================
class LoginWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("局域网聊天 - 登录")
        self.root.geometry("360x280")
        self.root.resizable(False, False)

        # 连接参数
        frm_conn = tk.LabelFrame(self.root, text="服务器设置", padx=5, pady=5)
        frm_conn.pack(fill="x", padx=10, pady=(10, 0))

        tk.Label(frm_conn, text="IP:").grid(row=0, column=0, sticky="e")
        self.entry_host = tk.Entry(frm_conn, width=20)
        self.entry_host.insert(0, DEFAULT_HOST)
        self.entry_host.grid(row=0, column=1, padx=5)

        tk.Label(frm_conn, text="端口:").grid(row=0, column=2, sticky="e")
        self.entry_port = tk.Entry(frm_conn, width=8)
        self.entry_port.insert(0, str(DEFAULT_PORT))
        self.entry_port.grid(row=0, column=3, padx=5)

        # 用户信息
        frm_auth = tk.LabelFrame(self.root, text="用户信息", padx=5, pady=5)
        frm_auth.pack(fill="x", padx=10, pady=5)

        tk.Label(frm_auth, text="用户名:").grid(row=0, column=0, sticky="e", pady=3)
        self.entry_user = tk.Entry(frm_auth, width=25)
        self.entry_user.grid(row=0, column=1, padx=5, pady=3)

        tk.Label(frm_auth, text="密  码:").grid(row=1, column=0, sticky="e", pady=3)
        self.entry_pass = tk.Entry(frm_auth, width=25, show="*")
        self.entry_pass.grid(row=1, column=1, padx=5, pady=3)

        # 按钮
        frm_btn = tk.Frame(self.root)
        frm_btn.pack(pady=10)
        tk.Button(frm_btn, text="登录", width=10, command=self.do_login).pack(side="left", padx=5)
        tk.Button(frm_btn, text="注册", width=10, command=self.do_register).pack(side="left", padx=5)

        self.socket = None
        self.username = None

        # 居中
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

    # ========================
    #  网络操作（静态方法，在后台线程中调用）
    # ========================
    @staticmethod
    def _connect(host, port_str):
        """连接服务器，返回 (socket, error_msg) — 不访问任何 tkinter 控件"""
        try:
            port = int(port_str)
        except ValueError:
            return None, "端口号必须为数字"
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.settimeout(10)
            return sock, None
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            return None, f"无法连接到服务器: {e}"

    @staticmethod
    def _send_and_recv(sock, msg_str):
        """发送消息并等待响应，返回 (resp_dict, error_msg) — 不访问任何 tkinter 控件"""
        try:
            sock.sendall(msg_str.encode(ENCODING))
            data = sock.recv(BUFFER_SIZE)
            resp = parse_message(data.decode(ENCODING))
            if resp is None:
                return None, "服务器返回了无效数据"
            return resp, None
        except socket.timeout:
            return None, "服务器响应超时，请确认服务端已启动"
        except Exception as e:
            return None, f"通信异常: {e}"

    # ========================
    #  登录 / 注册（主线程读取控件值 → 后台线程执行网络操作）
    # ========================
    def do_login(self):
        # 在主线程中读取所有 tkinter 控件值
        host = self.entry_host.get().strip()
        port = self.entry_port.get().strip()
        username = self.entry_user.get().strip()
        password = self.entry_pass.get().strip()
        if not username or not password:
            messagebox.showwarning("提示", "请输入用户名和密码")
            return

        def _run():
            sock, err = self._connect(host, port)
            if sock is None:
                self.root.after(0, lambda e=err: messagebox.showerror("错误", e))
                return
            resp, err = self._send_and_recv(
                sock, make_message(TYPE_LOGIN, username=username, password=password)
            )
            if resp and resp.get("status") == STATUS_OK:
                sock.settimeout(None)  # 聊天窗口需要长期保持连接，取消超时
                self.socket = sock
                self.username = username
                self._login_public_history = resp.get("public_history", [])
                self._login_conversations = resp.get("conversations", [])
                self._login_groups = resp.get("groups", [])
                self.root.after(0, self.root.destroy)
            else:
                msg = resp.get("message", "") if resp else err
                self.root.after(0, lambda m=msg: messagebox.showerror("登录失败", m))
                try:
                    sock.close()
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()

    def do_register(self):
        # 在主线程中读取所有 tkinter 控件值
        host = self.entry_host.get().strip()
        port = self.entry_port.get().strip()
        username = self.entry_user.get().strip()
        password = self.entry_pass.get().strip()
        if not username or not password:
            messagebox.showwarning("提示", "请输入用户名和密码")
            return

        def _run():
            sock, err = self._connect(host, port)
            if sock is None:
                self.root.after(0, lambda e=err: messagebox.showerror("错误", e))
                return
            resp, err = self._send_and_recv(
                sock, make_message(TYPE_REGISTER, username=username, password=password)
            )
            if resp and resp.get("status") == STATUS_OK:
                self.root.after(0, lambda: messagebox.showinfo("成功", "注册成功！请登录"))
            else:
                msg = resp.get("message", "") if resp else err
                self.root.after(0, lambda m=msg: messagebox.showerror("注册失败", m))
            try:
                sock.close()
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def run(self):
        self.root.mainloop()
        return self


# ============================
#  聊天主窗口
# ============================
class ChatWindow:
    def __init__(self, socket_conn, username, public_history=None, conversations=None, groups=None):
        self.socket = socket_conn
        self.username = username
        self.running = True
        self.current_chat = "public"
        self.online_users = set()
        self._conv_partners = list(conversations) if conversations else []
        self._groups = groups or []
        self._pending_upload = None

        self.root = tk.Tk()
        self.bubble_font = tkfont.Font(family=FONT_FAMILY, size=10)
        self.time_font = tkfont.Font(family=FONT_FAMILY, size=8)
        self.root.title(f"局域网聊天 - {username}")
        self.root.geometry("800x550")
        self.root.configure(bg=BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # PanedWindow 分左右
        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL,
                                     sashrelief=tk.RAISED, sashwidth=1, bg=BG_COLOR)
        self.paned.pack(fill=tk.BOTH, expand=True)

        self._build_left_panel()
        self._build_right_panel()

        # 会话列表初始渲染（同步填充）
        self._rebuild_conv_list()
        self.conv_tree.selection_set("public")
        self._on_tree_select()

        # 加载公聊历史
        if public_history:
            self._render_history(public_history)

        # 接收线程
        self.recv_thread = threading.Thread(target=self.receive_loop, daemon=True)
        self.recv_thread.start()

        # 居中
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

        self.refresh_users()

    def _build_left_panel(self):
        self.left_frame = tk.Frame(self.paned, width=200, bg=LEFT_BG)
        self.paned.add(self.left_frame, minsize=150)
        self.left_frame.pack_propagate(False)

        # 搜索框
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._filter_conversations())
        self.search_entry = tk.Entry(self.left_frame, textvariable=self.search_var,
                                      font=(FONT_FAMILY, 9), fg=GRAY)
        self.search_entry.insert(0, "搜索")
        self.search_entry.bind("<FocusIn>", lambda e: self._on_search_focus_in())
        self.search_entry.bind("<FocusOut>", lambda e: self._on_search_focus_out())
        self.search_entry.pack(fill="x", padx=8, pady=(8, 4))

        # Treeview 替代 Listbox
        self.conv_tree = ttk.Treeview(self.left_frame, show="tree",
                                       selectmode="browse", height=20)
        self.conv_tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        self.conv_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.conv_tree.bind("<Button-3>", self._on_tree_right_click)
        self._tree_menu = tk.Menu(self.left_frame, tearoff=0)

        # 根节点
        self.tree_root = self.conv_tree.insert("", "end", text="", open=True, iid="root")

        # 公聊大厅
        self.tree_public = self.conv_tree.insert("root", "end", iid="public", text="★ 公聊大厅")

        # 群聊父节点
        self.tree_groups = self.conv_tree.insert("root", "end", iid="groups", text="▼ 群聊", open=True)
        self._group_tree_ids = {}

        # 联系人父节点
        self.tree_contacts = self.conv_tree.insert("root", "end", iid="contacts", text="▼ 联系人", open=True)
        self._contact_tree_ids = []

        # 底部按钮
        btn_frame = tk.Frame(self.left_frame, bg=LEFT_BG)
        btn_frame.pack(fill="x", padx=4, pady=(0, 4))
        tk.Button(btn_frame, text="+ 创建群", font=(FONT_FAMILY, 9),
                 bg=LEFT_BG, relief=tk.GROOVE, cursor="hand2",
                 command=self._create_group_dialog).pack(fill="x")

    def _build_right_panel(self):
        self.right_frame = tk.Frame(self.paned, bg=BG_COLOR)
        self.paned.add(self.right_frame, minsize=400)

        # 标题栏
        self.title_bar = tk.Frame(self.right_frame, height=44, bg=BG_COLOR)
        self.title_bar.pack(fill="x", padx=12, pady=(8, 0))
        self.title_bar.pack_propagate(False)
        self.title_label = tk.Label(self.title_bar, text="公聊大厅",
                                     font=(FONT_FAMILY, 12, "bold"), bg=BG_COLOR, fg=BLACK)
        self.title_label.pack(side="left", pady=6)

        # 分割线
        sep = tk.Frame(self.right_frame, height=1, bg="#E0E0E0")
        sep.pack(fill="x", padx=12)

        # 聊天气泡区 (Canvas + Scrollbar)
        self.chat_container = tk.Frame(self.right_frame, bg=BG_COLOR)
        self.chat_container.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        self.chat_canvas = tk.Canvas(self.chat_container, bg=BG_COLOR, highlightthickness=0)
        self.chat_scrollbar = tk.Scrollbar(self.chat_container, orient=tk.VERTICAL,
                                            command=self.chat_canvas.yview)
        self.chat_canvas.configure(yscrollcommand=self.chat_scrollbar.set)

        self.chat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Canvas 内部 frame 用于放置气泡
        self.bubble_frame = tk.Frame(self.chat_canvas, bg=BG_COLOR)
        self.bubble_frame.bind("<Configure>",
            lambda e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all")))
        self.canvas_window = self.chat_canvas.create_window((0, 0), window=self.bubble_frame,
                                                             anchor="nw", tags="bubble_frame")
        self.chat_canvas.bind("<Configure>", self._on_canvas_resize)

        # 鼠标滚轮
        self.chat_canvas.bind("<Enter>", lambda e: self._bind_mousewheel())
        self.chat_canvas.bind("<Leave>", lambda e: self._unbind_mousewheel())

        # 输入区
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
                                    command=self._show_emoji_panel, bg=BG_COLOR, fg=BLACK,
                                    font=(FONT_FAMILY, 12), relief=tk.FLAT, cursor="hand2")
        self.emoji_btn.pack(side=tk.RIGHT, ipady=2)

    def _wrap_text(self, text, max_width):
        """将文本按像素宽度换行"""
        lines = []
        current = ""
        for char in text:
            if self.bubble_font.measure(current + char) <= max_width:
                current += char
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
        return lines if lines else [""]

    def _on_canvas_resize(self, event):
        self.chat_canvas.itemconfig(self.canvas_window, width=event.width)

    def _bind_mousewheel(self):
        self.chat_canvas.bind_all("<MouseWheel>",
            lambda e: self.chat_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def _unbind_mousewheel(self):
        self.chat_canvas.unbind_all("<MouseWheel>")

    def _render_bubble(self, sender, content, timestamp_str):
        """在 bubble_frame 中渲染一条聊天气泡"""
        is_me = (sender == self.username)
        is_system = (sender == "[系统]")

        if is_system:
            lbl = tk.Label(self.bubble_frame, text=content, font=self.time_font,
                          fg=BLUE_SYSTEM, bg=BG_COLOR)
            lbl.pack(pady=2)
            return

        max_text_width = 380
        lines = self._wrap_text(content, max_text_width)
        bubble_bg = GREEN_BUBBLE if is_me else WHITE

        # 气泡容器
        bubble_outer = tk.Frame(self.bubble_frame, bg=BG_COLOR)
        if is_me:
            bubble_outer.pack(anchor="e", pady=1, padx=(40, 6))
        else:
            bubble_outer.pack(anchor="w", pady=1, padx=(6, 40))

        # 发送者名（对方的消息显示名字）
        if not is_me:
            name_lbl = tk.Label(bubble_outer, text=sender, font=self.time_font,
                               fg=GRAY, bg=BG_COLOR, anchor="w")
            name_lbl.pack(anchor="w", padx=(4, 0))

        # 气泡体
        inner = tk.Frame(bubble_outer, bg=bubble_bg)
        inner.pack(anchor="e" if is_me else "w")

        for line in lines:
            lbl = tk.Label(inner, text=line, font=self.bubble_font,
                          bg=bubble_bg, fg=BLACK, justify=tk.LEFT)
            lbl.pack(anchor="w", padx=10, pady=(1, 0))

        # 时间戳
        ts = self._format_time(timestamp_str)
        ts_lbl = tk.Label(bubble_outer, text=ts, font=self.time_font,
                         fg=GRAY, bg=BG_COLOR)
        if is_me:
            ts_lbl.pack(anchor="e", padx=(0, 4))
        else:
            ts_lbl.pack(anchor="w", padx=(4, 0))

    def _add_bubble(self, sender, content, timestamp_str):
        """添加单条气泡（实时消息，线程安全）"""
        def _add():
            self._render_bubble(sender, content, timestamp_str)
            self._scroll_to_bottom()
        self.root.after(0, _add)

    def _format_time(self, ts_str):
        """将 ISO 时间戳转为 HH:MM"""
        try:
            dt = datetime.fromisoformat(ts_str)
            local = dt.astimezone()
            return local.strftime("%H:%M")
        except Exception:
            return ""

    def _scroll_to_bottom(self):
        self.chat_canvas.after(50, lambda: self.chat_canvas.yview_moveto(1.0))

    def _rebuild_conv_list(self):
        def _rebuild():
            # 清空联系人和群子节点
            for iid in self._contact_tree_ids:
                self.conv_tree.delete(iid)
            self._contact_tree_ids.clear()
            for iid in self._group_tree_ids.values():
                self.conv_tree.delete(iid)
            self._group_tree_ids.clear()

            tree = self.conv_tree
            # 群列表
            for g in getattr(self, '_groups', []):
                iid = f"group:{g['id']}"
                self._group_tree_ids[g['id']] = tree.insert(
                    self.tree_groups, "end", iid=iid, text=f"  {g['name']}",
                )
            # 联系人列表（含在线状态）
            for p in self._conv_partners:
                online = p in self.online_users
                prefix = "● " if online else "○ "
                iid = f"contact:{p}"
                tree.insert(self.tree_contacts, "end", iid=iid, text=f"  {prefix}{p}")
                self._contact_tree_ids.append(iid)
        self.root.after(0, _rebuild)

    def _render_history(self, messages):
        """渲染一组历史消息到气泡区"""
        self._clear_bubbles()
        for m in messages:
            self._render_bubble(
                m.get("sender", "未知"),
                m.get("content", ""),
                m.get("timestamp", ""),
            )
        self._scroll_to_bottom()

    def _clear_bubbles(self):
        """清空气泡区"""
        for w in self.bubble_frame.winfo_children():
            w.destroy()

    def _on_tree_select(self, event=None):
        sel = self.conv_tree.selection()
        if not sel:
            return
        iid = sel[0]
        target = None
        if iid == "public":
            self.current_chat = "public"
            self.title_label.config(text="公聊大厅")
            target = "public"
        elif iid.startswith("group:"):
            gid = int(iid.split(":")[1])
            self.current_chat = f"group:{gid}"
            for g in getattr(self, '_groups', []):
                if g['id'] == gid:
                    self.title_label.config(text=g['name'])
                    break
            target = self.current_chat
        elif iid.startswith("contact:"):
            partner = iid.split(":", 1)[1]
            self.current_chat = partner
            self.title_label.config(text=partner)
            target = partner
        else:
            return
        if target:
            try:
                self.socket.sendall(
                    make_message(TYPE_GET_HISTORY, target=target).encode(ENCODING)
                )
            except Exception:
                pass

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
            self._tree_menu.add_command(label="查看成员", command=lambda g=gid: self._show_group_members(g))
            self._tree_menu.add_command(label="退出群", command=lambda g=gid: self._leave_group(g))
            if grp.get("created_by") == self.username:
                self._tree_menu.add_command(label="解散群", command=lambda g=gid: self._delete_group(g))
        elif item.startswith("contact:"):
            self._tree_menu.add_command(label="发起私聊", command=lambda: self._on_tree_select())
        self._tree_menu.post(event.x_root, event.y_root)

    def _create_group_dialog(self):
        name = simpledialog.askstring("创建群聊", "请输入群名:", parent=self.root)
        if not name or not name.strip():
            return
        try:
            self.socket.sendall(
                make_message(TYPE_CREATE_GROUP, name=name.strip()).encode(ENCODING)
            )
        except Exception as e:
            self._add_bubble("[系统]", f"创建群失败: {e}", "")

    def _show_group_members(self, gid):
        try:
            self.socket.sendall(
                make_message(TYPE_GROUP_USERS, group_id=gid).encode(ENCODING)
            )
        except Exception:
            pass

    def _leave_group(self, gid):
        try:
            self.socket.sendall(
                make_message(TYPE_LEAVE_GROUP, group_id=gid).encode(ENCODING)
            )
        except Exception:
            pass
        self._groups = [g for g in self._groups if g['id'] != gid]
        self._rebuild_conv_list()

    def _delete_group(self, gid):
        try:
            self.socket.sendall(
                make_message(TYPE_DELETE_GROUP, group_id=gid).encode(ENCODING)
            )
        except Exception:
            pass
        self._groups = [g for g in self._groups if g['id'] != gid]
        self._rebuild_conv_list()

    def _switch_to(self, chat_key):
        """切换当前会话并加载历史"""
        self.current_chat = chat_key
        try:
            self.socket.sendall(
                make_message(TYPE_GET_HISTORY, target=chat_key).encode(ENCODING)
            )
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

    def refresh_users(self):
        """请求在线用户列表"""
        try:
            self.socket.sendall(
                make_message(TYPE_GET_USERS).encode(ENCODING)
            )
        except Exception:
            pass

    # ========================
    #  界面更新（线程安全）
    # ========================
    def _update_users(self, users):
        def _upd():
            self.online_users = set(users)
        self.root.after(0, _upd)

    # ========================
    #  消息接收循环
    # ========================
    def receive_loop(self):
        """后台线程：持续接收服务器消息"""
        buffer = ""
        decoder = json.JSONDecoder()
        while self.running:
            try:
                data = self.socket.recv(BUFFER_SIZE)
                if not data:
                    self._add_bubble("[系统]", "与服务器断开连接", "")
                    break
                buffer += data.decode(ENCODING)
                while buffer:
                    stripped = buffer.lstrip()
                    if not stripped:
                        buffer = ""
                        break
                    try:
                        obj, end = decoder.raw_decode(stripped)
                        buffer = stripped[end:]
                        self._handle_message(obj)
                    except json.JSONDecodeError:
                        break
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                if self.running:
                    self._add_bubble("[系统]", "与服务器断开连接", "")
                break
            except Exception as e:
                if self.running:
                    self._add_bubble("[系统]", f"接收异常: {e}", "")
                break

    def _handle_message(self, msg):
        msg_type = msg.get("type")
        if msg_type == TYPE_BROADCAST:
            sender = msg.get("sender", "未知")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            if sender == "[系统]":
                # 系统消息始终显示
                self._add_bubble(sender, content, ts)
            elif self.current_chat == "public":
                self._add_bubble(sender, content, ts)

        elif msg_type == TYPE_PRIVATE:
            sender = msg.get("sender", "未知")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            target = msg.get("target", "")
            partner = target if sender == self.username else sender
            # 显示在当前会话中
            if self.current_chat == partner or self.current_chat == sender:
                self._add_bubble(sender, content, ts)
            # 将联系人加入左侧列表
            if partner != self.username and partner not in self._conv_partners:
                self._conv_partners.append(partner)
                self._rebuild_conv_list()

        elif msg_type == TYPE_HISTORY:
            resp_target = msg.get("target", "")
            if resp_target == self.current_chat:
                self.root.after(0, lambda m=msg: self._render_history(m.get("messages", [])))

        elif msg_type == TYPE_GET_USERS:
            self._update_users(msg.get("users", []))

        elif msg_type == TYPE_RESPONSE:
            # 群创建/加入响应
            group_data = msg.get("group")
            if group_data:
                exist = [g for g in self._groups if g['id'] == group_data['id']]
                if not exist:
                    self._groups.append(group_data)
                self._rebuild_conv_list()
                self.root.after(100, lambda gid=group_data['id']: self._switch_to(f"group:{gid}"))

        elif msg_type == TYPE_GROUP_USERS:
            users = msg.get("users", [])
            gid = msg.get("group_id")
            self.root.after(0, lambda: messagebox.showinfo(
                f"群成员 (id={gid})", "\n".join(users),
            ))

        elif msg_type == TYPE_GROUP_MSG:
            sender = msg.get("sender", "未知")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            gid = msg.get("group_id")
            if self.current_chat == f"group:{gid}":
                self._add_bubble(sender, content, ts)

    def _show_emoji_panel(self):
        """弹出 emoji 选择面板"""
        panel = tk.Toplevel(self.root)
        panel.title("")
        panel.overrideredirect(True)
        panel.attributes("-topmost", True)
        panel.configure(bg=WHITE)

        # 计算位置（在 emoji 按钮上方弹出）
        x = self.emoji_btn.winfo_rootx()
        y = self.emoji_btn.winfo_rooty() - 200
        panel.geometry(f"240x300+{x}+{y}")

        # 6 列 x 9 行 emoji 网格
        cols = 6
        for i, em in enumerate(EMOJI_LIST):
            row = i // cols
            col = i % cols
            btn = tk.Button(panel, text=em, font=(FONT_FAMILY, 12),
                           bg=WHITE, relief=tk.FLAT, cursor="hand2",
                           command=lambda e=em: self._insert_emoji(e, panel))
            btn.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
            for c in range(cols):
                panel.grid_columnconfigure(c, weight=1)

        # 点击面板外部关闭
        def on_focus_out(event):
            if event.widget == panel:
                panel.destroy()
        panel.bind("<FocusOut>", on_focus_out)
        panel.focus_set()

    def _insert_emoji(self, emoji, panel):
        """将 emoji 插入输入框并关闭面板"""
        pos = self.entry_msg.index(tk.INSERT)
        self.entry_msg.insert(pos, emoji)
        panel.destroy()
        self.entry_msg.focus_set()

    # ========================
    #  发送消息
    # ========================
    def send_message(self, event=None):
        content = self.entry_msg.get().strip()
        if not content:
            return
        self.entry_msg.delete(0, "end")

        # 私聊: @用户名 消息
        if content.startswith("@"):
            parts = content.split(" ", 1)
            if len(parts) >= 2:
                target = parts[0][1:]
                msg_content = parts[1]
                ts = datetime.now(timezone.utc).isoformat()
                msg = make_message(TYPE_PRIVATE, target=target, content=msg_content,
                                   timestamp=ts)
                try:
                    self.socket.sendall(msg.encode(ENCODING))
                except Exception as e:
                    self._add_bubble("[系统]", f"发送失败: {e}", "")
                    return
                # 服务端会回显私聊消息给发送方，无需本地回声
                # 确保目标在左侧列表
                if target not in self._conv_partners:
                    self._conv_partners.append(target)
                    self._rebuild_conv_list()
                return
            else:
                self._add_bubble("[系统]", "私聊格式: @用户名 消息内容", "")
                return

        # 公聊
        ts = datetime.now(timezone.utc).isoformat()
        msg = make_message(TYPE_BROADCAST, content=content, timestamp=ts)
        try:
            self.socket.sendall(msg.encode(ENCODING))
        except Exception as e:
            self._add_bubble("[系统]", f"发送失败: {e}", "")
            return
        # 本地回显（公聊不排除自己，回声只在当前公聊显示）
        self._add_bubble(self.username, content, ts)

    # ========================
    #  关闭窗口
    # ========================
    def on_close(self):
        self.running = False
        try:
            self.socket.close()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ============================
#  入口
# ============================
if __name__ == "__main__":
    login = LoginWindow()
    login.run()

    if login.username and login.socket:
        chat = ChatWindow(
            login.socket, login.username,
            public_history=getattr(login, '_login_public_history', []),
            conversations=getattr(login, '_login_conversations', []),
            groups=getattr(login, '_login_groups', []),
        )
        chat.run()
