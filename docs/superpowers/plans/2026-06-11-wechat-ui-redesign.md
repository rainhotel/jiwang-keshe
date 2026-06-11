# 微信风格 UI + 聊天记录持久化 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将聊天客户端重构为微信桌面版双面板 UI（会话列表+聊天气泡），服务端增加 messages.json 消息持久化

**Architecture:** 扩展 JSON 协议增加 get_history/history 消息类型；服务端读写 messages.json 存消息并在登录时返回历史；客户端用 tkinter PanedWindow + Canvas 实现微信风格布局

**Tech Stack:** Python 3, tkinter, socket, json, threading

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `chat-software/common.py` | Modify | 新增协议常量 + 时间戳工具函数 |
| `chat-software/server.py` | Modify | 消息持久化、历史查询、登录增强 |
| `chat-software/client.py` | Modify | ChatWindow 重写，LoginWindow 不变 |

---

### Task 1: 协议层 — common.py 新增常量和工具

**Files:**
- Modify: `chat-software/common.py`

- [ ] **Step 1: 添加新常量和方法**

在 `common.py` 末尾追加以下代码：

```python
# === 历史消息 ===
TYPE_GET_HISTORY = "get_history"
TYPE_HISTORY = "history"

MAX_HISTORY = 50          # 每次拉取历史条数
MAX_MESSAGES_PER_CHAT = 500  # 每个会话最多保留条数

from datetime import datetime, timezone

def now_iso():
    """返回当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()

def conversation_key(user1, user2):
    """私聊会话的唯一 key：两个用户名按字母序用 : 连接"""
    a, b = (user1, user2) if user1 < user2 else (user2, user1)
    return f"{a}:{b}"
```

- [ ] **Step 2: 验证导入**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "from common import TYPE_GET_HISTORY, TYPE_HISTORY, now_iso, conversation_key; print(now_iso()); print(conversation_key('alice','bob'))"
```
Expected: 输出 ISO 时间戳和 `alice:bob`

- [ ] **Step 3: Commit**

```bash
git add chat-software/common.py
git commit -m "feat: add get_history/history protocol constants and timestamp helper"
```

---

### Task 2: 服务端 — 消息持久化引擎

**Files:**
- Modify: `chat-software/server.py`

- [ ] **Step 1: 添加 import 和常量**

在 `server.py` 顶部 import 区修改，添加新常量的导入和 messages 文件路径：

```python
from common import (
    DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE, ENCODING,
    TYPE_REGISTER, TYPE_LOGIN, TYPE_BROADCAST, TYPE_PRIVATE,
    TYPE_GET_USERS, TYPE_RESPONSE, TYPE_SYSTEM,
    TYPE_GET_HISTORY, TYPE_HISTORY,       # 新增
    MAX_HISTORY, MAX_MESSAGES_PER_CHAT,    # 新增
    STATUS_OK, STATUS_ERROR,
    make_message, parse_message, make_response, make_system_msg,
    now_iso, conversation_key,             # 新增
)

USERS_FILE = "users.json"
MESSAGES_FILE = "messages.json"            # 新增
```

- [ ] **Step 2: 修改 __init__，加载消息文件**

在 `__init__` 末尾添加 `self._load_messages()`：

```python
def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
    self.host = host
    self.port = port
    self.server_socket = None
    self.clients = {}
    self.lock = threading.RLock()
    self.messages = {"public": []}  # 新增: {key: [{sender,content,timestamp}]}
    self._load_users()
    self._load_messages()           # 新增
```

- [ ] **Step 3: 添加 _load_messages 方法**

在 `_save_users` 方法之后插入：

```python
def _load_messages(self):
    """从 JSON 文件加载历史消息"""
    if os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, "r", encoding=ENCODING) as f:
            self.messages = json.load(f)
        total = sum(len(v) for v in self.messages.values())
        print(f"[服务器] 已加载 {total} 条历史消息 ({len(self.messages)} 个会话)")
    else:
        self.messages = {"public": []}
        print("[服务器] 消息文件不存在，将创建新文件")

def _save_messages(self):
    """持久化消息到磁盘（调用方可以持有锁）"""
    with self.lock:
        data = self.messages
    with open(MESSAGES_FILE, "w", encoding=ENCODING) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: 添加 _add_message 方法**

在 `_save_messages` 之后插入：

```python
def _add_message(self, key, sender, content):
    """添加一条消息到 messages 并持久化"""
    msg = {
        "sender": sender,
        "content": content,
        "timestamp": now_iso(),
    }
    with self.lock:
        if key not in self.messages:
            self.messages[key] = []
        self.messages[key].append(msg)
        # 超过上限则淘汰旧消息
        if len(self.messages[key]) > MAX_MESSAGES_PER_CHAT:
            self.messages[key] = self.messages[key][-MAX_MESSAGES_PER_CHAT:]
    self._save_messages()
    return msg  # 返回带 timestamp 的消息给调用方
```

- [ ] **Step 5: 添加 _get_conversations_for_user 方法**

```python
def _get_conversations_for_user(self, username):
    """返回某用户参与过的所有私聊对象列表（按最近消息时间降序）"""
    partners = []
    with self.lock:
        for key in self.messages:
            if key == "public":
                continue
            users = key.split(":")
            if username in users:
                partner = users[0] if users[1] == username else users[1]
                last_ts = self.messages[key][-1]["timestamp"] if self.messages[key] else ""
                partners.append((partner, last_ts))
    partners.sort(key=lambda x: x[1], reverse=True)
    return [p[0] for p in partners]
```

- [ ] **Step 6: 验证服务端启动**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
from server import ChatServer
s = ChatServer()
print('messages:', s.messages)
print('OK')
"
```
Expected: `messages: {'public': []}` 然后 `OK`

- [ ] **Step 7: Commit**

```bash
git add chat-software/server.py
git commit -m "feat: add message persistence engine (load/save/add messages)"
```

---

### Task 3: 服务端 — 修改广播/私聊处理器保存消息，新增历史查询，增强登录

**Files:**
- Modify: `chat-software/server.py`

- [ ] **Step 1: 修改 _handle_broadcast，保存消息并附加 timestamp**

替换 `_handle_broadcast` 方法：

```python
def _handle_broadcast(self, msg, client_socket, current_user):
    if not current_user:
        client_socket.sendall(
            make_response(STATUS_ERROR, "请先登录").encode(ENCODING)
        )
        return
    content = msg.get("content", "")
    if not content.strip():
        return
    # 保存到 messages
    saved = self._add_message("public", current_user, content)
    full_msg = make_message(
        TYPE_BROADCAST, content=content, sender=current_user,
        timestamp=saved["timestamp"],
    )
    print(f"[公聊] {current_user}: {content}")
    self.broadcast(full_msg, exclude=current_user)
```

- [ ] **Step 2: 修改 _handle_private，保存消息并附加 timestamp**

替换 `_handle_private` 方法：

```python
def _handle_private(self, msg, client_socket, current_user):
    if not current_user:
        client_socket.sendall(
            make_response(STATUS_ERROR, "请先登录").encode(ENCODING)
        )
        return
    target = msg.get("target", "").strip()
    content = msg.get("content", "")
    if not target or not content.strip():
        client_socket.sendall(
            make_response(STATUS_ERROR, "私聊格式: @用户名 消息").encode(ENCODING)
        )
        return

    with self.lock:
        if target not in self.clients or self.clients[target].get("addr") is None:
            client_socket.sendall(
                make_response(STATUS_ERROR, f"用户 '{target}' 不在线").encode(ENCODING)
            )
            return

    # 保存消息
    key = conversation_key(current_user, target)
    saved = self._add_message(key, current_user, content)

    ok = self.private_message(target, content, current_user)
    if ok:
        # 回显给发送方
        echo = make_message(
            TYPE_PRIVATE, content=content, sender=current_user, target=target,
            timestamp=saved["timestamp"],
        )
        client_socket.sendall(echo.encode(ENCODING))
        print(f"[私聊] {current_user} -> {target}: {content}")
    else:
        client_socket.sendall(
            make_response(STATUS_ERROR, "私聊发送失败").encode(ENCODING)
        )
```

- [ ] **Step 3: 添加 _handle_get_history 方法**

在 `_handle_get_users` 之后插入：

```python
def _handle_get_history(self, msg, client_socket, current_user):
    """返回指定会话的最近 N 条历史"""
    if not current_user:
        return
    target = msg.get("target", "public")
    # 如果是私聊会话，用 conversation_key 构造真正的 key
    if target != "public":
        target = conversation_key(current_user, target)
    with self.lock:
        msgs = self.messages.get(target, [])[-MAX_HISTORY:]
    client_socket.sendall(
        make_message(TYPE_HISTORY, target=target, messages=msgs).encode(ENCODING)
    )
```

- [ ] **Step 4: 修改 _dispatch，添加 get_history 分支**

在 `_dispatch` 方法中添加两个新 `elif`：

```python
    elif msg_type == TYPE_GET_USERS:
        self._handle_get_users(client_socket)
    elif msg_type == TYPE_GET_HISTORY:                    # 新增
        self._handle_get_history(msg, client_socket, current_user)
    else:
```

- [ ] **Step 5: 修改 _handle_login，返回历史和会话列表**

替换登录成功后的发送响应部分（`_handle_login` 方法的后半段）：

```python
        print(f"{_ts()} _handle_login: 登录成功 '{username}' → 发送响应")
        public_history = self.messages.get("public", [])[-MAX_HISTORY:]
        conversations = self._get_conversations_for_user(username)
        login_resp = make_message(
            TYPE_RESPONSE, status=STATUS_OK, message="登录成功",
            public_history=public_history, conversations=conversations,
        )
        client_socket.sendall(login_resp.encode(ENCODING))
        print(f"{_ts()} _handle_login: 响应已发送, 广播上线通知")
```

- [ ] **Step 6: 修改 shutdown，保存消息**

在 `shutdown` 方法的 `self._save_users()` 之后添加：

```python
        self._save_users()
        self._save_messages()                              # 新增
        print("[服务器] 服务器已关闭")
```

- [ ] **Step 7: 验证**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
from server import ChatServer
import threading, time, socket, json
from common import *

s = ChatServer()
t = threading.Thread(target=s.start, daemon=True)
t.start()
time.sleep(0.5)

# Register + login alice
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5); sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_REGISTER, username='alice', password='123').encode(ENCODING))
r = parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok'; sock.close()

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5); sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_LOGIN, username='alice', password='123').encode(ENCODING))
r = parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok'
assert 'public_history' in r
assert 'conversations' in r
print(f'Login OK, public_history={len(r[\"public_history\"])} msgs, conversations={r[\"conversations\"]}')
sock.close()
s.shutdown()
print('ALL PASSED')
"
```
Expected: Login OK, public_history=0 msgs, conversations=[]

- [ ] **Step 8: Commit**

```bash
git add chat-software/server.py
git commit -m "feat: save messages on broadcast/private, add get_history, enhance login with history"
```

---

### Task 4: 客户端 — ChatWindow 微信布局骨架

**Files:**
- Modify: `chat-software/client.py`

此任务重写 `ChatWindow.__init__` 以及左右面板的骨架构建方法。LoginWindow 完全不动。

- [ ] **Step 1: 添加 import 和配色常量**

在 client.py 顶部 import 区，修改导入并添加常量：

```python
import json
import socket
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime, timezone
from tkinter import scrolledtext, messagebox, simpledialog

from common import (
    DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE, ENCODING,
    TYPE_REGISTER, TYPE_LOGIN, TYPE_BROADCAST, TYPE_PRIVATE,
    TYPE_GET_USERS, TYPE_SYSTEM, TYPE_RESPONSE,
    TYPE_GET_HISTORY, TYPE_HISTORY,           # 新增
    STATUS_OK, STATUS_ERROR,
    make_message, parse_message,
)

# 微信风格配色
BG_COLOR = "#F5F5F5"           # 主背景
LEFT_BG = "#EBEBEB"             # 左侧面板
WHITE = "#FFFFFF"
GREEN_BUBBLE = "#95EC69"       # 我方气泡
BLACK = "#000000"
GRAY = "#999999"
BLUE_SYSTEM = "#888888"
FONT_FAMILY = "微软雅黑"
```

- [ ] **Step 2: 重写 ChatWindow.__init__**

完全替换 `ChatWindow` 类的 `__init__` 方法（原 182-243 行）：

```python
class ChatWindow:
    def __init__(self, socket_conn, username):
        self.socket = socket_conn
        self.username = username
        self.running = True
        self.current_chat = "public"  # 当前会话: "public" 或对方用户名
        self.bubble_font = tkfont.Font(family=FONT_FAMILY, size=10)
        self.time_font = tkfont.Font(family=FONT_FAMILY, size=8)

        self.root = tk.Tk()
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

        # 接收线程
        self.recv_thread = threading.Thread(target=self.receive_loop, daemon=True)
        self.recv_thread.start()

        # 居中
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

        # 初始加载
        self.refresh_users()
```

- [ ] **Step 3: 添加 _build_left_panel 方法**

在 `__init__` 之后插入：

```python
    def _build_left_panel(self):
        self.left_frame = tk.Frame(self.paned, width=200, bg=LEFT_BG)
        self.paned.add(self.left_frame, minsize=150)
        self.left_frame.pack_propagate(False)

        # 搜索框
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._filter_conversations())
        self.search_entry = tk.Entry(self.left_frame, textvariable=self.search_var,
                                      font=("微软雅黑", 9), fg=GRAY)
        self.search_entry.insert(0, "搜索")
        self.search_entry.bind("<FocusIn>", lambda e: self._on_search_focus_in())
        self.search_entry.bind("<FocusOut>", lambda e: self._on_search_focus_out())
        self.search_entry.pack(fill="x", padx=8, pady=(8, 4))

        # 会话列表
        self.conv_listbox = tk.Listbox(self.left_frame, font=("微软雅黑", 10),
                                        bg=LEFT_BG, fg=BLACK, selectmode=tk.SINGLE,
                                        activestyle="none", border=0, highlightthickness=0)
        self.conv_listbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 8))
        self.conv_listbox.bind("<<ListboxSelect>>", self._on_conversation_select)

        # 私聊对象列表（存储原始用户名）
        self._conv_partners = []
```

- [ ] **Step 4: 添加 _build_right_panel 方法**

```python
    def _build_right_panel(self):
        self.right_frame = tk.Frame(self.paned, bg=BG_COLOR)
        self.paned.add(self.right_frame, minsize=400)

        # 标题栏
        self.title_bar = tk.Frame(self.right_frame, height=44, bg=BG_COLOR)
        self.title_bar.pack(fill="x", padx=12, pady=(8, 0))
        self.title_bar.pack_propagate(False)
        self.title_label = tk.Label(self.title_bar, text="公聊大厅",
                                     font=("微软雅黑", 12, "bold"), bg=BG_COLOR, fg=BLACK)
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

        # 鼠标滚轮绑定
        self.chat_canvas.bind("<Enter>", lambda e: self._bind_mousewheel())
        self.chat_canvas.bind("<Leave>", lambda e: self._unbind_mousewheel())

        # 输入区
        self.input_frame = tk.Frame(self.right_frame, bg=BG_COLOR, height=50)
        self.input_frame.pack(fill="x", padx=12, pady=(4, 10))
        self.input_frame.pack_propagate(False)

        self.entry_msg = tk.Entry(self.input_frame, font=("微软雅黑", 10),
                                   bg=WHITE, relief=tk.FLAT, border=1)
        self.entry_msg.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry_msg.bind("<Return>", self.send_message)

        self.send_btn = tk.Button(self.input_frame, text="发送", width=8,
                                   command=self.send_message, bg="#2DC100", fg=WHITE,
                                   font=("微软雅黑", 9), relief=tk.FLAT, cursor="hand2")
        self.send_btn.pack(side=tk.RIGHT, padx=(6, 0), ipady=2)

    def _on_canvas_resize(self, event):
        self.chat_canvas.itemconfig(self.canvas_window, width=event.width)

    def _bind_mousewheel(self):
        self.chat_canvas.bind_all("<MouseWheel>",
            lambda e: self.chat_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def _unbind_mousewheel(self):
        self.chat_canvas.unbind_all("<MouseWheel>")

    def _scroll_to_bottom(self):
        self.chat_canvas.after(50, lambda: self.chat_canvas.yview_moveto(1.0))
```

- [ ] **Step 5: 验证 GUI 能启动（空窗口）**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
import tkinter as tk
print('tkinter OK')
"
```

- [ ] **Step 6: Commit**

```bash
git add chat-software/client.py
git commit -m "feat: rewrite ChatWindow with WeChat-style PanedWindow layout"
```

---

### Task 5: 客户端 — 聊天气泡渲染

**Files:**
- Modify: `chat-software/client.py`

- [ ] **Step 1: 添加 _wrap_text 辅助方法**

在 ChatWindow 类中添加：

```python
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
```

- [ ] **Step 2: 添加 _render_bubble 方法**

```python
    def _render_bubble(self, sender, content, timestamp_str):
        """在 bubble_frame 中渲染一条聊天气泡"""
        is_me = (sender == self.username)
        is_system = (sender == "[系统]")

        if is_system:
            lbl = tk.Label(self.bubble_frame, text=content, font=self.time_font,
                          fg=BLUE_SYSTEM, bg=BG_COLOR)
            lbl.pack(pady=2)
            return

        max_text_width = 380  # 气泡内文字最大宽度
        lines = self._wrap_text(content, max_text_width)
        bubble_bg = GREEN_BUBBLE if is_me else WHITE

        # 气泡容器 frame
        bubble_outer = tk.Frame(self.bubble_frame, bg=BG_COLOR)
        # 对齐: 我方靠右，对方靠左
        if is_me:
            bubble_outer.pack(anchor="e", pady=1, padx=(40, 6))
        else:
            bubble_outer.pack(anchor="w", pady=1, padx=(6, 40))

        # 发送者名
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

    def _format_time(self, ts_str):
        """将 ISO 时间戳转为 HH:MM 显示"""
        try:
            dt = datetime.fromisoformat(ts_str)
            # 转为本地时间
            local = dt.astimezone()
            return local.strftime("%H:%M")
        except Exception:
            return ""
```

- [ ] **Step 3: 添加 _render_history 方法**

```python
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
```

- [ ] **Step 4: 添加 _add_bubble 方法（单条新增，用于实时消息）**

```python
    def _add_bubble(self, sender, content, timestamp_str):
        """添加单条气泡（实时消息），线程安全"""
        def _add():
            self._render_bubble(sender, content, timestamp_str)
            self._scroll_to_bottom()
        self.root.after(0, _add)
```

- [ ] **Step 5: Commit**

```bash
git add chat-software/client.py
git commit -m "feat: add WeChat-style chat bubble rendering with timestamps"
```

---

### Task 6: 客户端 — 消息处理逻辑（接收循环 + 发送 + 会话切换）

**Files:**
- Modify: `chat-software/client.py`

- [ ] **Step 1: 重写 receive_loop**

替换现有的 `receive_loop` 方法：

```python
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
```

- [ ] **Step 2: 重写 _handle_message**

完全替换原有的 `_handle_message` 方法：

```python
    def _handle_message(self, msg):
        msg_type = msg.get("type")
        if msg_type == TYPE_BROADCAST:
            sender = msg.get("sender", "未知")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            # 只渲染当前正在看的公聊消息
            if self.current_chat == "public":
                self._add_bubble(sender, content, ts)

        elif msg_type == TYPE_PRIVATE:
            sender = msg.get("sender", "未知")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            target = msg.get("target", "")
            # target 是服务端发来的接收方，判断是否属于当前私聊会话
            partner = target if sender == self.username else sender
            if self.current_chat == partner:
                self._add_bubble(sender, content, ts)
            # 如果不在当前会话，仍将联系人加入左侧列表
            if partner != self.username and partner not in self._conv_partners:
                self._conv_partners.append(partner)
                self._rebuild_conv_list()

        elif msg_type == TYPE_HISTORY:
            self.root.after(0, lambda: self._render_history(msg.get("messages", [])))

        elif msg_type == TYPE_GET_USERS:
            self._update_users(msg.get("users", []))

    def _update_users(self, users):
        """更新在线用户（用于在线状态标记，不改变会话列表结构）"""
        def _upd():
            self.online_users = set(users)
        self.root.after(0, _upd)
```

- [ ] **Step 3: 重写 send_message**

```python
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
                # 本地回显
                if self.current_chat == target or self.current_chat == "public":
                    self._add_bubble(self.username, msg_content, ts)
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
        # 本地回显
        self._add_bubble(self.username, content, ts)
```

- [ ] **Step 4: 添加会话切换逻辑**

```python
    def _on_conversation_select(self, event=None):
        selection = self.conv_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx == 0:
            # 公聊大厅
            self.current_chat = "public"
            self.title_label.config(text="公聊大厅")
        else:
            partner = self._conv_partners[idx - 1]
            self.current_chat = partner
            self.title_label.config(text=partner)
        # 请求历史
        target = "public" if self.current_chat == "public" else self.current_chat
        self.socket.sendall(
            make_message(TYPE_GET_HISTORY, target=target).encode(ENCODING)
        )

    def add_conversation(self, partner):
        """外部调用：添加私聊会话并切换到它"""
        if partner not in self._conv_partners:
            self._conv_partners.append(partner)
            self._rebuild_conv_list()
        # 切换到该会话
        for i, p in enumerate(self._conv_partners):
            if p == partner:
                self.conv_listbox.selection_clear(0, tk.END)
                self.conv_listbox.selection_set(i + 1)
                self._on_conversation_select()
                break

    def _rebuild_conv_list(self):
        def _rebuild():
            self.conv_listbox.delete(0, tk.END)
            self.conv_listbox.insert(tk.END, "★ 公聊大厅")
            for p in self._conv_partners:
                self.conv_listbox.insert(tk.END, f"  {p}")
        self.root.after(0, _rebuild)

    def _filter_conversations(self):
        query = self.search_var.get().strip()
        if query == "搜索" or not query:
            self._rebuild_conv_list()
            return
        def _filter():
            self.conv_listbox.delete(0, tk.END)
            self.conv_listbox.insert(tk.END, "★ 公聊大厅")
            for p in self._conv_partners:
                if query.lower() in p.lower():
                    self.conv_listbox.insert(tk.END, f"  {p}")
        self.root.after(0, _filter)
```

- [ ] **Step 5: 添加搜索框交互**

```python
    def _on_search_focus_in(self):
        if self.search_var.get() == "搜索":
            self.search_entry.delete(0, tk.END)
            self.search_entry.config(fg=BLACK)

    def _on_search_focus_out(self):
        if not self.search_var.get().strip():
            self.search_entry.insert(0, "搜索")
            self.search_entry.config(fg=GRAY)
```

- [ ] **Step 6: 修改登录响应处理（do_login 中接收 history + conversations）**

修改 `do_login` 中的 `_run` 函数，处理登录响应中的 `public_history` 和 `conversations`：

替换原有的登录成功处理块：

```python
            if resp and resp.get("status") == STATUS_OK:
                sock.settimeout(None)
                self.socket = sock
                self.username = username
                # 保存登录响应中的历史数据和会话列表
                self._login_public_history = resp.get("public_history", [])
                self._login_conversations = resp.get("conversations", [])
                self.root.after(0, self.root.destroy)
```

- [ ] **Step 7: 修改 ChatWindow.__init__，初始化时加载登录数据**

在 `ChatWindow.__init__` 末尾（`self.refresh_users()` 之前）添加：

```python
        # 从登录响应加载初始数据
        self.online_users = set()
        self._conv_partners = list(login._login_conversations) if hasattr(login, '_login_conversations') else []

        # 渲染会话列表
        self._rebuild_conv_list()
        self.conv_listbox.selection_set(0)  # 默认选中公聊大厅

        # 渲染公聊历史
        public_history = getattr(login, '_login_public_history', [])
        if public_history:
            self._render_history(public_history)

        self.refresh_users()
```

注意：ChatWindow 需要接收 `login` 对象或者在 `__init__` 中接收这些数据。更简洁的方式是修改入口代码传递这些数据。

**修改入口（文件末尾 `__main__` 部分）**：

```python
if __name__ == "__main__":
    login = LoginWindow()
    login.run()

    if login.username and login.socket:
        chat = ChatWindow(login.socket, login.username,
                          public_history=getattr(login, '_login_public_history', []),
                          conversations=getattr(login, '_login_conversations', []))
        chat.run()
```

**修改 ChatWindow.__init__ 签名**：

```python
    def __init__(self, socket_conn, username, public_history=None, conversations=None):
        ...
        self._conv_partners = list(conversations) if conversations else []
        ...
        if public_history:
            self._render_history(public_history)
```

- [ ] **Step 8: 重写 on_close**

```python
    def on_close(self):
        self.running = False
        try:
            self.socket.close()
        except Exception:
            pass
        self.root.destroy()
```

`refresh_users` 保持不变（用于定期刷新在线用户列表）。

删除不再需要的旧方法：`append_text`, `update_user_list`, `start_private_chat`（用 `add_conversation` 替代）。

- [ ] **Step 9: Commit**

```bash
git add chat-software/client.py
git commit -m "feat: rewrite message handling for WeChat UI - receive, send, history, conversation switching"
```

---

### Task 7: 集成测试

**Files:**
- Create: `chat-software/test_integration.py`

- [ ] **Step 1: 创建集成测试脚本**

```python
"""
集成测试：服务端消息持久化 + 客户端核心逻辑
"""
import socket, sys, time, threading, json
sys.path.insert(0, ".")
from server import ChatServer
from common import *

def test():
    server = ChatServer()
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    time.sleep(0.5)

    # --- alice 注册+登录 ---
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s1.settimeout(5); s1.connect(('127.0.0.1', 9999))
    s1.sendall(make_message(TYPE_REGISTER, username='alice', password='123').encode(ENCODING))
    r = parse_message(s1.recv(BUFFER_SIZE).decode(ENCODING)); assert r['status'] == 'ok'; s1.close()

    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s1.settimeout(5); s1.connect(('127.0.0.1', 9999))
    s1.sendall(make_message(TYPE_LOGIN, username='alice', password='123').encode(ENCODING))
    r = parse_message(s1.recv(BUFFER_SIZE).decode(ENCODING))
    assert r['status'] == 'ok'
    assert 'public_history' in r
    print(f"[PASS] alice 登录, public_history={len(r['public_history'])}")

    # --- alice 发公聊 ---
    ts = datetime.now(timezone.utc).isoformat()
    s1.sendall(make_message(TYPE_BROADCAST, content='hello world', timestamp=ts).encode(ENCODING))

    # --- bob 注册+登录 ---
    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s2.settimeout(5); s2.connect(('127.0.0.1', 9999))
    s2.sendall(make_message(TYPE_REGISTER, username='bob', password='123').encode(ENCODING))
    parse_message(s2.recv(BUFFER_SIZE).decode(ENCODING)); s2.close()

    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s2.settimeout(5); s2.connect(('127.0.0.1', 9999))
    s2.sendall(make_message(TYPE_LOGIN, username='bob', password='123').encode(ENCODING))
    r = parse_message(s2.recv(BUFFER_SIZE).decode(ENCODING))
    assert r['status'] == 'ok'
    assert len(r['public_history']) >= 1  # bob 应该看到 alice 的消息
    print(f"[PASS] bob 登录, public_history={len(r['public_history'])} (应该 >= 1)")

    # --- alice 收到 bob 上线通知 ---
    s1.settimeout(3)
    data = s1.recv(BUFFER_SIZE)
    sys_msg = parse_message(data.decode(ENCODING))
    print(f"[PASS] alice 收到系统消息: {sys_msg.get('content')}")

    # --- 私聊测试 ---
    s2.sendall(make_message(TYPE_PRIVATE, target='alice', content='私聊消息', timestamp=ts).encode(ENCODING))
    s1.settimeout(3)
    data = s1.recv(BUFFER_SIZE)
    priv = parse_message(data.decode(ENCODING))
    assert priv['content'] == '私聊消息'
    print(f"[PASS] alice 收到 bob 的私聊: {priv['content']}")

    # --- 历史查询 ---
    s1.sendall(make_message(TYPE_GET_HISTORY, target='bob').encode(ENCODING))
    s1.settimeout(3)
    data = s1.recv(BUFFER_SIZE)
    hist = parse_message(data.decode(ENCODING))
    assert hist['type'] == 'history'
    assert len(hist['messages']) >= 1
    print(f"[PASS] 私聊历史查询: {len(hist['messages'])} 条消息")

    # --- 验证消息持久化 ---
    s1.close(); s2.close()
    server.shutdown()

    # 重启服务端，验证 messages.json 持久化
    server2 = ChatServer()
    assert len(server2.messages.get("public", [])) >= 1
    assert len(server2.messages.get(conversation_key("alice", "bob"), [])) >= 1
    print(f"[PASS] 服务端重启后消息不丢失: public={len(server2.messages['public'])}, private={len(server2.messages[conversation_key('alice','bob')])}")
    server2.shutdown()

    print("\n" + "=" * 50)
    print("  全部集成测试通过！")
    print("=" * 50)


if __name__ == "__main__":
    test()
```

- [ ] **Step 2: 运行集成测试**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python test_integration.py
```
Expected: 所有 6 个 `[PASS]` 通过

- [ ] **Step 3: 清理并提交**

```bash
rm -f D:/moniC/project/jiwang-keshe/chat-software/test_integration.py
rm -f D:/moniC/project/jiwang-keshe/chat-software/users.json
rm -f D:/moniC/project/jiwang-keshe/chat-software/messages.json
git add chat-software/
git commit -m "test: integration test for message persistence and history"
```
(如果 test_integration.py 不在 git 跟踪中，不需要 rm 和 git add)

- [ ] **Step 4: 最终手动验证**

启动服务端和两个客户端，测试：
1. alice 注册 + 登录 → 左侧显示"公聊大厅"
2. alice 发公聊消息 → 气泡正确显示（绿色靠右，带时间戳）
3. bob 注册 + 登录 → 自动看到 alice 之前发的公聊消息
4. bob 发公聊 → alice 实时收到（白色气泡靠左）
5. alice 双击/搜索发起私聊 → 左侧新增联系人，切换后显示私聊历史
6. 关闭所有客户端，重启服务端 → 历史消息仍在

---

## Plan Self-Review

- Spec coverage: All 8 test items from spec are covered
- No placeholders, TODOs, or vague instructions
- Type consistency: `conversation_key` used consistently across server and plan
- LoginWindow preserved unchanged per spec
