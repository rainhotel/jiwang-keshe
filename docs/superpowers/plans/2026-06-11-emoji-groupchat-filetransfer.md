# Emoji + 群聊 + 文件传输 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为聊天软件添加 emoji 面板、群聊系统、文件传输三个功能

**Architecture:** 按依赖顺序依次实现。emoji 纯客户端改动；群聊新增协议+DB表，左侧面板从 Listbox 改为 Treeview；文件传输新增独立 TCP 端口(9998)+二进制流协议

**Tech Stack:** Python 3, tkinter, socket, sqlite3, threading, uuid

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `chat-software/common.py` | Modify | 群聊+文件传输协议常量 |
| `chat-software/server.py` | Modify | 群聊 handlers、文件端口、新表 |
| `chat-software/client.py` | Modify | emoji 面板、Treeview 左侧面板、群聊 UI、文件 UI |

---

### Task 1: Emoji — 常量和按钮

**Files:**
- Modify: `chat-software/client.py`

- [ ] **Step 1: 添加 EMOJI_LIST 常量**

在 client.py 配色常量区（第 31 行之后）插入：

```python
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
```

- [ ] **Step 2: 添加 emoji 按钮到输入区**

在 `_build_right_panel` 中，修改 send_btn 前插入 emoji 按钮。定位到第 319-322 行：

原代码：
```python
        self.send_btn = tk.Button(self.input_frame, text="发送", width=8,
                                   command=self.send_message, bg="#2DC100", fg=WHITE,
                                   font=(FONT_FAMILY, 9), relief=tk.FLAT, cursor="hand2")
        self.send_btn.pack(side=tk.RIGHT, padx=(6, 0), ipady=2)
```

改为：
```python
        self.send_btn = tk.Button(self.input_frame, text="发送", width=8,
                                   command=self.send_message, bg="#2DC100", fg=WHITE,
                                   font=(FONT_FAMILY, 9), relief=tk.FLAT, cursor="hand2")
        self.send_btn.pack(side=tk.RIGHT, padx=(6, 0), ipady=2)

        self.emoji_btn = tk.Button(self.input_frame, text="😀", width=4,
                                    command=self._show_emoji_panel, bg=BG_COLOR, fg=BLACK,
                                    font=(FONT_FAMILY, 12), relief=tk.FLAT, cursor="hand2")
        self.emoji_btn.pack(side=tk.RIGHT, ipady=2)
```

- [ ] **Step 3: 验证按钮显示**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
import tkinter as tk; r = tk.Tk(); r.destroy()
from client import EMOJI_LIST
assert len(EMOJI_LIST) == 54
print(f'EMOJI_LIST OK: {len(EMOJI_LIST)} emojis')
"
```
Expected: `EMOJI_LIST OK: 54 emojis`

- [ ] **Step 4: Commit**

```bash
git add chat-software/client.py
git commit -m "feat: add emoji list constant and emoji button to input bar"
```

---

### Task 2: Emoji — 弹出选择面板

**Files:**
- Modify: `chat-software/client.py`

- [ ] **Step 1: 添加 _show_emoji_panel 方法**

在 `send_message` 方法之前插入：

```python
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
```

- [ ] **Step 2: 确认 emoji 在气泡中正常渲染**

emoji 是 Unicode，渲染走现有 `_render_bubble` → `_wrap_text` 路径，Unicode 字符宽度计算兼容。

- [ ] **Step 3: Commit**

```bash
git add chat-software/client.py
git commit -m "feat: add emoji popup panel with grid selection"
```

---

### Task 3: 群聊 — 协议常量 + 数据库

**Files:**
- Modify: `chat-software/common.py`
- Modify: `chat-software/server.py`

- [ ] **Step 1: 添加群聊协议常量到 common.py**

在 common.py 的 `# === 历史消息相关常量 ===` 区域，`MAX_MESSAGES_PER_CHAT` 之后插入：

```python
# === 群聊相关常量 ===
TYPE_CREATE_GROUP = "create_group"   # → {"name": "..."}
TYPE_JOIN_GROUP   = "join_group"     # → {"group_id": 3}
TYPE_LEAVE_GROUP  = "leave_group"    # → {"group_id": 3}
TYPE_DELETE_GROUP = "delete_group"   # → {"group_id": 3}
TYPE_GROUP_USERS  = "group_users"    # → {"group_id": 3}
TYPE_GROUP_MSG    = "group_msg"      # → {"group_id": 3, "content": "...", "timestamp": "..."}

def group_key(group_id):
    """群聊 chat_key"""
    return f"group:{group_id}"
```

- [ ] **Step 2: 添加 groups 和 group_members 表到 server.py**

在 `_init_db` 中的现有 `self.conn.commit()` 之前插入：

```python
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id  INTEGER,
                username  TEXT,
                joined_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (group_id, username)
            )
        """)
```

- [ ] **Step 3: 更新 server.py import 行**

在 server.py 的 `from common import ...` 中添加新常量。定位到第 13-22 行，添加：

```python
from common import (
    DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE, ENCODING,
    TYPE_REGISTER, TYPE_LOGIN, TYPE_BROADCAST, TYPE_PRIVATE,
    TYPE_GET_USERS, TYPE_RESPONSE, TYPE_SYSTEM,
    TYPE_GET_HISTORY, TYPE_HISTORY,
    TYPE_CREATE_GROUP, TYPE_JOIN_GROUP, TYPE_LEAVE_GROUP,  # 新增
    TYPE_DELETE_GROUP, TYPE_GROUP_USERS, TYPE_GROUP_MSG,    # 新增
    MAX_HISTORY, MAX_MESSAGES_PER_CHAT,
    STATUS_OK, STATUS_ERROR,
    make_message, parse_message, make_response, make_system_msg,
    now_iso, conversation_key, group_key,                    # 新增
)
```

- [ ] **Step 4: 验证启动**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
from common import TYPE_CREATE_GROUP, group_key
assert group_key(3) == 'group:3'
print(f'group_key(3) = {group_key(3)}')

from server import ChatServer
s = ChatServer()
tables = s.conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print('tables:', [t[0] for t in tables])
s.conn.close()
"
```
Expected: `tables: ['users', 'messages', 'groups', 'group_members']`

- [ ] **Step 5: Commit**

```bash
git add chat-software/common.py chat-software/server.py
git commit -m "feat: add group chat protocol constants and groups/group_members tables"
```

---

### Task 4: 群聊 — 服务端处理器

**Files:**
- Modify: `chat-software/server.py`

- [ ] **Step 1: 添加 _handle_create_group**

在 `_handle_get_history` 方法之后插入：

```python
    # ========================
    #  群聊管理
    # ========================
    def _handle_create_group(self, msg, client_socket, current_user):
        if not current_user:
            return
        name = msg.get("name", "").strip()
        if not name:
            client_socket.sendall(
                make_response(STATUS_ERROR, "群名不能为空").encode(ENCODING)
            )
            return
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO groups (name, created_by) VALUES (?, ?)",
                (name, current_user),
            )
            gid = cur.lastrowid
            self.conn.execute(
                "INSERT INTO group_members (group_id, username) VALUES (?, ?)",
                (gid, current_user),
            )
            self.conn.commit()
        client_socket.sendall(
            make_message(TYPE_RESPONSE, status=STATUS_OK, message="群创建成功",
                        group={"id": gid, "name": name, "created_by": current_user}).encode(ENCODING)
        )
        print(f"[群聊] {current_user} 创建了群 '{name}' (id={gid})")

    def _handle_join_group(self, msg, client_socket, current_user):
        if not current_user:
            return
        gid = msg.get("group_id")
        if not gid:
            return
        with self.lock:
            # 检查群是否存在
            row = self.conn.execute("SELECT id, name FROM groups WHERE id=?", (gid,)).fetchone()
            if not row:
                client_socket.sendall(
                    make_response(STATUS_ERROR, "群不存在").encode(ENCODING)
                )
                return
            # 检查是否已在群中
            exist = self.conn.execute(
                "SELECT 1 FROM group_members WHERE group_id=? AND username=?",
                (gid, current_user),
            ).fetchone()
            if exist:
                client_socket.sendall(
                    make_response(STATUS_ERROR, "你已在该群中").encode(ENCODING)
                )
                return
            self.conn.execute(
                "INSERT INTO group_members (group_id, username) VALUES (?, ?)",
                (gid, current_user),
            )
            self.conn.commit()
        gname = row[1]
        client_socket.sendall(
            make_message(TYPE_RESPONSE, status=STATUS_OK, message=f"已加入群 '{gname}'",
                        group={"id": gid, "name": gname}).encode(ENCODING)
        )
        print(f"[群聊] {current_user} 加入了群 '{gname}' (id={gid})")

    def _handle_leave_group(self, msg, client_socket, current_user):
        if not current_user:
            return
        gid = msg.get("group_id")
        if not gid:
            return
        with self.lock:
            self.conn.execute(
                "DELETE FROM group_members WHERE group_id=? AND username=?",
                (gid, current_user),
            )
            self.conn.commit()
        client_socket.sendall(
            make_response(STATUS_OK, "已退出群").encode(ENCODING)
        )
        print(f"[群聊] {current_user} 退出了群 (id={gid})")

    def _handle_delete_group(self, msg, client_socket, current_user):
        if not current_user:
            return
        gid = msg.get("group_id")
        if not gid:
            return
        with self.lock:
            row = self.conn.execute(
                "SELECT created_by FROM groups WHERE id=?", (gid,)
            ).fetchone()
            if not row:
                client_socket.sendall(
                    make_response(STATUS_ERROR, "群不存在").encode(ENCODING)
                )
                return
            if row[0] != current_user:
                client_socket.sendall(
                    make_response(STATUS_ERROR, "只有群创建者可以解散群").encode(ENCODING)
                )
                return
            self.conn.execute("DELETE FROM group_members WHERE group_id=?", (gid,))
            self.conn.execute("DELETE FROM groups WHERE id=?", (gid,))
            self.conn.commit()
        client_socket.sendall(
            make_response(STATUS_OK, "群已解散").encode(ENCODING)
        )
        print(f"[群聊] {current_user} 解散了群 (id={gid})")

    def _handle_group_users(self, msg, client_socket, current_user):
        if not current_user:
            return
        gid = msg.get("group_id")
        if not gid:
            return
        rows = self.conn.execute(
            "SELECT username FROM group_members WHERE group_id=?", (gid,)
        ).fetchall()
        members = [r[0] for r in rows]
        client_socket.sendall(
            make_message(TYPE_GROUP_USERS, group_id=gid, users=members).encode(ENCODING)
        )
```

- [ ] **Step 2: 添加群消息处理 _handle_group_msg**

在 `_handle_group_users` 之后插入：

```python
    def _handle_group_msg(self, msg, client_socket, current_user):
        if not current_user:
            return
        gid = msg.get("group_id")
        content = msg.get("content", "")
        if not gid or not content.strip():
            return
        # 检查是否群成员
        member = self.conn.execute(
            "SELECT 1 FROM group_members WHERE group_id=? AND username=?",
            (gid, current_user),
        ).fetchone()
        if not member:
            client_socket.sendall(
                make_response(STATUS_ERROR, "你不是该群成员").encode(ENCODING)
            )
            return

        key = group_key(gid)
        saved = self._add_message_db(key, current_user, content)
        full_msg = make_message(
            TYPE_GROUP_MSG, group_id=gid, content=content, sender=current_user,
            timestamp=saved["timestamp"],
        )
        # 广播给群内所有在线成员
        rows = self.conn.execute(
            "SELECT username FROM group_members WHERE group_id=?", (gid,)
        ).fetchall()
        data = full_msg.encode(ENCODING)
        with self.lock:
            for (uname,) in rows:
                info = self.clients.get(uname)
                if info and info.get("socket"):
                    try:
                        info["socket"].sendall(data)
                    except Exception:
                        pass
        print(f"[群聊-{gid}] {current_user}: {content}")
```

- [ ] **Step 3: 扩展 _dispatch**

在 `_dispatch` 中添加群聊分支。定位到 `TYPE_GET_HISTORY` 分支之后（第 222 行），添加：

```python
        elif msg_type == TYPE_CREATE_GROUP:
            self._handle_create_group(msg, client_socket, current_user)
        elif msg_type == TYPE_JOIN_GROUP:
            self._handle_join_group(msg, client_socket, current_user)
        elif msg_type == TYPE_LEAVE_GROUP:
            self._handle_leave_group(msg, client_socket, current_user)
        elif msg_type == TYPE_DELETE_GROUP:
            self._handle_delete_group(msg, client_socket, current_user)
        elif msg_type == TYPE_GROUP_USERS:
            self._handle_group_users(msg, client_socket, current_user)
        elif msg_type == TYPE_GROUP_MSG:
            self._handle_group_msg(msg, client_socket, current_user)
```

- [ ] **Step 4: 验证**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
from server import ChatServer
import threading, time, socket
from common import *
s = ChatServer()
t = threading.Thread(target=s.start, daemon=True); t.start()
time.sleep(0.5)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5)
sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_REGISTER, username='alice', password='123').encode(ENCODING))
r = parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING)); assert r['status'] == 'ok'; sock.close()

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5)
sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_LOGIN, username='alice', password='123').encode(ENCODING))
parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING))
sock.sendall(make_message(TYPE_CREATE_GROUP, name='test群').encode(ENCODING))
r = parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok', f'create failed: {r}'
print(f'PASS: create group: {r}')
sock.close()
s.shutdown()
print('ALL PASSED')
"
```
Expected: `PASS: create group: {'type': 'response', ...}`

- [ ] **Step 5: Commit**

```bash
git add chat-software/server.py
git commit -m "feat: add group chat handlers (create/join/leave/delete/msg/users)"
```

---

### Task 5: 群聊 — 登录增强 + 历史兼容

**Files:**
- Modify: `chat-software/server.py`

- [ ] **Step 1: 修改 _handle_login，返回用户群列表**

在 `_handle_login` 中，`conversations = self._get_conversations_for_user(username)` 之后添加群列表查询，并合并到响应中。

定位到第 318 行，修改登录响应构造：

```python
        # 查询用户所在的群
        gids = self.conn.execute(
            "SELECT group_id FROM group_members WHERE username=?", (username,)
        ).fetchall()
        groups = []
        for (gid,) in gids:
            grp = self.conn.execute("SELECT id, name, created_by FROM groups WHERE id=?", (gid,)).fetchone()
            if grp:
                mems = self.conn.execute(
                    "SELECT username FROM group_members WHERE group_id=?", (gid,)
                ).fetchall()
                groups.append({
                    "id": grp[0], "name": grp[1], "created_by": grp[2],
                    "members": [m[0] for m in mems],
                })
        login_resp = make_message(
            TYPE_RESPONSE, status=STATUS_OK, message="登录成功",
            public_history=public_history, conversations=conversations, groups=groups,
        )
```

- [ ] **Step 2: 修改 _handle_get_history 支持群聊**

`_handle_get_history` 中，`target` 对私聊的转换逻辑需要兼容群聊 key。定位到第 457-459 行：

```python
        target = msg.get("target", "public")
        if target != "public":
            target = conversation_key(current_user, target)
```

改为：

```python
        target = msg.get("target", "public")
        # group:xxx 格式不需要转换，直接使用
        if target != "public" and not target.startswith("group:"):
            target = conversation_key(current_user, target)
```

- [ ] **Step 3: 验证**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
from server import ChatServer
import threading, time, socket
from common import *
s = ChatServer()
t = threading.Thread(target=s.start, daemon=True); t.start()
time.sleep(0.5)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5)
sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_REGISTER, username='alice', password='123').encode(ENCODING))
parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING)); sock.close()

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5)
sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_LOGIN, username='alice', password='123').encode(ENCODING))
r = parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING))
assert 'groups' in r, f'no groups field: {list(r.keys())}'
assert r['groups'] == [], f'groups should be empty: {r[\"groups\"]}'
print(f'PASS: login with groups field, groups={r[\"groups\"]}')
sock.close()
s.shutdown()
print('ALL PASSED')
"
```
Expected: `PASS: login with groups field, groups=[]`

- [ ] **Step 4: Commit**

```bash
git add chat-software/server.py
git commit -m "feat: return user groups on login, support group key in get_history"
```

---

### Task 6: 群聊 — 客户端左侧面板 Treeview

**Files:**
- Modify: `chat-software/client.py`

- [ ] **Step 1: 添加 import ttk**

在 client.py 顶部，`import tkinter as tk` 行后追加：

```python
from tkinter import ttk
```

- [ ] **Step 2: 重写 _build_left_panel，用 Treeview 替代 Listbox**

替换 `_build_left_panel` 方法（第 246-267 行）：

```python
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

        # 根节点
        self.tree_root = self.conv_tree.insert("", "end", text="", open=True, iid="root")

        # 公聊大厅
        self.tree_public = self.conv_tree.insert("root", "end", iid="public", text="★ 公聊大厅")

        # 群聊父节点
        self.tree_groups = self.conv_tree.insert("root", "end", iid="groups", text="▼ 群聊", open=True)
        self._group_tree_ids = {}  # {group_id: tree_iid}

        # 联系人父节点
        self.tree_contacts = self.conv_tree.insert("root", "end", iid="contacts", text="▼ 联系人", open=True)
        self._contact_tree_ids = []  # iid list for rebuilder

        # 底部按钮
        btn_frame = tk.Frame(self.left_frame, bg=LEFT_BG)
        btn_frame.pack(fill="x", padx=4, pady=(0, 4))
        tk.Button(btn_frame, text="+ 创建群", font=(FONT_FAMILY, 9),
                 bg=LEFT_BG, relief=tk.GROOVE, cursor="hand2",
                 command=self._create_group_dialog).pack(fill="x")
```

- [ ] **Step 3: 重写 _rebuild_conv_list**

```python
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
```

- [ ] **Step 4: 添加 Treeview 选择事件处理**

```python
    def _on_tree_select(self, event=None):
        sel = self.conv_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "public":
            self.current_chat = "public"
            self.title_label.config(text="公聊大厅")
        elif iid.startswith("group:"):
            gid = int(iid.split(":")[1])
            self.current_chat = f"group:{gid}"
            # 获取群名
            for g in getattr(self, '_groups', []):
                if g['id'] == gid:
                    self.title_label.config(text=g['name'])
                    break
        elif iid.startswith("contact:"):
            partner = iid.split(":", 1)[1]
            self.current_chat = partner
            self.title_label.config(text=partner)
        else:
            return
        # 请求历史
        try:
            self.socket.sendall(
                make_message(TYPE_GET_HISTORY, target=self.current_chat).encode(ENCODING)
            )
        except Exception:
            pass
```

- [ ] **Step 5: 修改 __init__，用 Treeview 初始化**

在 `__init__` 中，会话列表初始渲染代码（第 222-227 行）替换如下。定位并替换：

原代码：
```python
        # 会话列表初始渲染（同步填充，不等 after 回调）
        self.conv_listbox.delete(0, tk.END)
        self.conv_listbox.insert(tk.END, "★ 公聊大厅")
        for p in self._conv_partners:
            self.conv_listbox.insert(tk.END, f"  {p}")
        self.conv_listbox.selection_set(0)
        self._on_conversation_select()
```

改为：
```python
        # 初始会话列表（同步填充）
        self._groups = getattr(login, '_login_groups', []) if 'login' in dir() else []
        self._rebuild_conv_list()
        self.conv_tree.selection_set("public")
        self._on_tree_select()
```

但 `login` 变量只在 `__main__` 中存在。正确做法：通过构造函数传入 groups。

**修改 __init__ 签名：**

```python
    def __init__(self, socket_conn, username, public_history=None, conversations=None, groups=None):
        ...
        self._conv_partners = list(conversations) if conversations else []
        self._groups = groups or []
```

**修改入口 `__main__`（第 646-651 行）：**

```python
        chat = ChatWindow(
            login.socket, login.username,
            public_history=getattr(login, '_login_public_history', []),
            conversations=getattr(login, '_login_conversations', []),
            groups=getattr(login, '_login_groups', []),
        )
```

**修改 LoginWindow.do_login（第 146 行之后）：**

```python
                self._login_public_history = resp.get("public_history", [])
                self._login_conversations = resp.get("conversations", [])
                self._login_groups = resp.get("groups", [])
```

- [ ] **Step 6: 修改 _handle_message 的 TYPE_HISTORY 分支**

原代码处理 `TYPE_HISTORY` 时只匹配 `current_chat` 字符串。需要兼容 group key：

```python
        elif msg_type == TYPE_HISTORY:
            resp_target = msg.get("target", "")
            if resp_target == self.current_chat or resp_target == "public":
                if self.current_chat == "public" or resp_target == self.current_chat:
                    self.root.after(0, lambda m=msg: self._render_history(m.get("messages", [])))
            elif resp_target != "public" and not resp_target.startswith("group:"):
                users = resp_target.split(":")
                if self.current_chat in users:
                    self.root.after(0, lambda m=msg: self._render_history(m.get("messages", [])))
```

改为简化版：

```python
        elif msg_type == TYPE_HISTORY:
            resp_target = msg.get("target", "")
            if resp_target == self.current_chat or self.current_chat == resp_target:
                self.root.after(0, lambda m=msg: self._render_history(m.get("messages", [])))
            elif self.current_chat == "public" and resp_target == "public":
                self.root.after(0, lambda m=msg: self._render_history(m.get("messages", [])))
```

- [ ] **Step 7: 验证导入**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "from client import ChatWindow; print('Import OK')"
```
Expected: `Import OK`

- [ ] **Step 8: Commit**

```bash
git add chat-software/client.py
git commit -m "feat: replace Listbox with Treeview for group/contact list"
```

---

### Task 7: 群聊 — 创建群弹窗 + 右键菜单

**Files:**
- Modify: `chat-software/client.py`

- [ ] **Step 1: 添加 _create_group_dialog 方法**

在 `_on_tree_select` 之后插入：

```python
    def _create_group_dialog(self):
        """弹出创建群对话框"""
        name = tk.simpledialog.askstring("创建群聊", "请输入群名:", parent=self.root)
        if not name or not name.strip():
            return
        try:
            self.socket.sendall(
                make_message(TYPE_CREATE_GROUP, name=name.strip()).encode(ENCODING)
            )
        except Exception as e:
            self._add_bubble("[系统]", f"创建群失败: {e}", "")
```

**注意**: 需要在 import 区加 `from tkinter import simpledialog`，但该模块已在第 12 行导入的 `messagebox` 同级。确认 import 有 `simpledialog`：

在第 12 行：
```python
from tkinter import messagebox
```

改为：
```python
from tkinter import messagebox, simpledialog
```

- [ ] **Step 2: 添加右键菜单**

在 `_build_left_panel` 中绑定右键菜单：

在 Treeview 创建代码（`self.conv_tree = ttk.Treeview(...)`）之后，绑定右键：

```python
        self.conv_tree.bind("<Button-3>", self._on_tree_right_click)
        self._tree_menu = tk.Menu(self.left_frame, tearoff=0)
```

添加 `_on_tree_right_click` 方法：

```python
    def _on_tree_right_click(self, event):
        item = self.conv_tree.identify_row(event.y)
        if not item or item in ("root", "public", "groups", "contacts"):
            return
        self.conv_tree.selection_set(item)

        self._tree_menu.delete(0, tk.END)
        if item.startswith("group:"):
            gid = int(item.split(":")[1])
            # 找群信息
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
        # 从本地列表移除
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
```

- [ ] **Step 3: 添加群相关消息处理**

在 `_handle_message` 中添加 `TYPE_RESPONSE` 处理（处理 group 相关响应），以及 `TYPE_GROUP_USERS` 处理。

在 `_handle_message` 中 `TYPE_RESPONSE` 分支（第 576 行之后）扩展：

```python
        elif msg_type == TYPE_RESPONSE:
            group_data = msg.get("group")
            if group_data:
                # 新建/加入群响应
                exist = [g for g in self._groups if g['id'] == group_data['id']]
                if not exist:
                    self._groups.append(group_data)
                self._rebuild_conv_list()
                # 切换到该群
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
```

添加 `_switch_to` 辅助方法：

```python
    def _switch_to(self, chat_key):
        """切换当前会话并加载历史"""
        self.current_chat = chat_key
        try:
            self.socket.sendall(
                make_message(TYPE_GET_HISTORY, target=chat_key).encode(ENCODING)
            )
        except Exception:
            pass
```

- [ ] **Step 4: Commit**

```bash
git add chat-software/client.py
git commit -m "feat: add group create dialog, right-click menu, group message handling"
```

---

### Task 8: 群聊 — 发送群消息

**Files:**
- Modify: `chat-software/client.py`

- [ ] **Step 1: 修改 send_message 支持群聊**

在 `send_message` 方法中，`@ 用户名` 私聊判断之后、公聊之前，添加群聊分支。定位到第 610 行附近（公聊分支之前）：

```python
        # 群聊
        if self.current_chat.startswith("group:"):
            gid = int(self.current_chat.split(":")[1])
            ts = datetime.now(timezone.utc).isoformat()
            msg = make_message(TYPE_GROUP_MSG, group_id=gid, content=content, timestamp=ts)
            try:
                self.socket.sendall(msg.encode(ENCODING))
            except Exception as e:
                self._add_bubble("[系统]", f"发送失败: {e}", "")
                return
            # 服务端会广播给所有群成员（包括自己），本地不重复渲染
            return
```

- [ ] **Step 2: 修改 _filter_conversations 兼容 Treeview**

```python
    def _filter_conversations(self):
        query = self.search_var.get().strip()
        if query == "搜索" or not query:
            self._rebuild_conv_list()
            return
        def _filter():
            # 清空群和联系人子节点
            for iid in self._contact_tree_ids:
                self.conv_tree.delete(iid)
            self._contact_tree_ids.clear()
            for iid in self._group_tree_ids.values():
                self.conv_tree.delete(iid)
            self._group_tree_ids.clear()
            # 过滤
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
```

- [ ] **Step 3: Commit**

```bash
git add chat-software/client.py
git commit -m "feat: add group message sending and treeview search filter"
```

---

### Task 9: 文件传输 — 服务端文件端口 + 协议

**Files:**
- Modify: `chat-software/common.py`
- Modify: `chat-software/server.py`

- [ ] **Step 1: 添加文件传输协议常量到 common.py**

在群聊常量之后插入：

```python
# === 文件传输相关常量 ===
TYPE_FILE_SEND    = "file_send"     # C→S: {"receiver": "...", "filename": "...", "size": N}
TYPE_FILE_NOTIFY  = "file_notify"   # S→C: {"file_id": "...", "filename": "...", "size": N, "sender": "..."}
TYPE_FILE_DOWNLOAD = "file_download" # C→S: {"file_id": "..."}

FILE_PORT = 9998
FILE_CHUNK = 65536  # 64KB per chunk
```

- [ ] **Step 2: 添加 files 表到 server.py 的 _init_db**

在 `_init_db` 中，`self.conn.commit()` 之前插入：

```python
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_id   TEXT PRIMARY KEY,
                filename  TEXT NOT NULL,
                size      INTEGER NOT NULL,
                sender    TEXT NOT NULL,
                receiver  TEXT NOT NULL,
                chat_key  TEXT NOT NULL,
                timestamp TEXT DEFAULT (datetime('now'))
            )
        """)
```

并在 `__init__` 中添加文件目录：

```python
        os.makedirs("files", exist_ok=True)
```

- [ ] **Step 3: 更新 server.py import**

在 `from common import ...` 中添加文件常量，并添加 `import uuid`：

```python
import uuid
```

以及 import 中添加：
```python
    TYPE_FILE_SEND, TYPE_FILE_NOTIFY, TYPE_FILE_DOWNLOAD,  # 新增
    FILE_PORT, FILE_CHUNK,                                   # 新增
```

- [ ] **Step 4: 添加文件端口监听器**

在 `start` 方法中添加文件端口线程：

在 `start` 方法中 `print("[服务器] 等待客户端连接...")` 之前插入：

```python
        # 启动文件传输端口
        file_thread = threading.Thread(target=self._start_file_server, daemon=True)
        file_thread.start()
        print(f"[服务器] 文件传输端口: {self.host}:{FILE_PORT}")
```

添加 `_start_file_server` 方法（在 `_add_message_db` 之后）：

```python
    def _start_file_server(self):
        """在 9998 端口处理文件上传/下载"""
        try:
            file_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            file_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            file_sock.bind((self.host, FILE_PORT))
            file_sock.listen(10)
            file_sock.settimeout(1.0)
            while True:
                try:
                    client, addr = file_sock.accept()
                    threading.Thread(target=self._handle_file_conn, args=(client, addr), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception:
                    break
        except Exception as e:
            print(f"[服务器] 文件端口启动失败: {e}")

    def _handle_file_conn(self, client, addr):
        """处理文件上传或下载"""
        try:
            header = b""
            while b"\n" not in header:
                chunk = client.recv(128)
                if not chunk:
                    return
                header += chunk
            file_id = header.decode(ENCODING).strip()

            # 检查 files 表：有记录 → 下载；无记录 → 上传
            row = self.conn.execute(
                "SELECT file_id, filename, size FROM files WHERE file_id=?", (file_id,)
            ).fetchone()
            if row:
                # 下载模式
                filepath = os.path.join("files", file_id)
                if os.path.exists(filepath):
                    with open(filepath, "rb") as f:
                        while True:
                            chunk = f.read(FILE_CHUNK)
                            if not chunk:
                                break
                            client.sendall(chunk)
                print(f"[文件] 下载完成: {row[1]} → {addr}")
            else:
                # 上传模式（等待后续 file_send 消息通过聊天通道注册 file_id）
                # 这里直接接收并存储，因为 file_id 由聊天通道注册
                filepath = os.path.join("files", file_id)
                received_size = 0
                with open(filepath, "wb") as f:
                    while True:
                        chunk = client.recv(FILE_CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        received_size += len(chunk)
                # 更新文件大小
                self.conn.execute(
                    "UPDATE files SET size=? WHERE file_id=?",
                    (received_size, file_id),
                )
                self.conn.commit()
                print(f"[文件] 上传完成: {filepath} ({received_size} bytes)")

                # 通知接收方
                row2 = self.conn.execute(
                    "SELECT receiver, filename, size, sender, chat_key FROM files WHERE file_id=?", (file_id,)
                ).fetchone()
                if row2:
                    receiver, filename, fsize, sender, chat_key = row2
                    with self.lock:
                        info = self.clients.get(receiver)
                        if info and info.get("socket"):
                            try:
                                info["socket"].sendall(make_message(
                                    TYPE_FILE_NOTIFY, file_id=file_id, filename=filename,
                                    size=fsize, sender=sender,
                                ).encode(ENCODING))
                            except Exception:
                                pass
        except Exception as e:
            print(f"[文件] 连接错误: {e}")
        finally:
            client.close()
```

- [ ] **Step 5: 添加 _handle_file_send 聊天通道处理器**

```python
    def _handle_file_send(self, msg, client_socket, current_user):
        """处理文件发送请求（通过聊天通道）"""
        if not current_user:
            return
        receiver = msg.get("receiver", "").strip()
        filename = msg.get("filename", "").strip()
        size = msg.get("size", 0)
        if not receiver or not filename:
            client_socket.sendall(
                make_response(STATUS_ERROR, "参数不完整").encode(ENCODING)
            )
            return

        file_id = str(uuid.uuid4())
        chat_key = conversation_key(current_user, receiver) if receiver != current_user else "public"
        self.conn.execute(
            "INSERT INTO files (file_id, filename, size, sender, receiver, chat_key) VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, filename, size, current_user, receiver, chat_key),
        )
        self.conn.commit()

        # 告知发送方 file_id，发送方随后通过 9998 端口上传
        client_socket.sendall(
            make_message(TYPE_RESPONSE, status=STATUS_OK, file_id=file_id).encode(ENCODING)
        )
        print(f"[文件] {current_user} → {receiver}: {filename} ({size} bytes, id={file_id})")

    def _handle_file_download(self, msg, client_socket, current_user):
        """处理文件下载请求"""
        if not current_user:
            return
        file_id = msg.get("file_id", "")
        if not file_id:
            return
        row = self.conn.execute(
            "SELECT file_id, filename FROM files WHERE file_id=?", (file_id,)
        ).fetchone()
        if not row:
            client_socket.sendall(
                make_response(STATUS_ERROR, "文件不存在").encode(ENCODING)
            )
            return
        client_socket.sendall(
            make_message(TYPE_RESPONSE, status=STATUS_OK, file_id=file_id).encode(ENCODING)
        )
```

- [ ] **Step 6: 在 _dispatch 中添加文件分支**

```python
        elif msg_type == TYPE_FILE_SEND:
            self._handle_file_send(msg, client_socket, current_user)
        elif msg_type == TYPE_FILE_DOWNLOAD:
            self._handle_file_download(msg, client_socket, current_user)
```

- [ ] **Step 7: 验证**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
from server import ChatServer
import threading, time, socket
from common import *
s = ChatServer()
t = threading.Thread(target=s.start, daemon=True); t.start()
time.sleep(0.5)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5)
sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_REGISTER, username='alice', password='123').encode(ENCODING))
parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING)); sock.close()

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5)
sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_LOGIN, username='alice', password='123').encode(ENCODING))
parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING))
sock.sendall(make_message(TYPE_FILE_SEND, receiver='alice', filename='test.txt', size=5).encode(ENCODING))
r = parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok', f'file_send failed: {r}'
fid = r['file_id']
print(f'PASS: file_send, file_id={fid}')

# upload via file port
fs = socket.socket(socket.AF_INET, socket.SOCK_STREAM); fs.settimeout(5)
fs.connect(('127.0.0.1', 9998))
fs.sendall((fid + '\n').encode(ENCODING))
fs.sendall(b'hello')
fs.close()
time.sleep(0.3)

# verify file saved
import os
assert os.path.exists(f'files/{fid}')
with open(f'files/{fid}', 'rb') as f:
    assert f.read() == b'hello'
print(f'PASS: file content verified')
sock.close()
s.shutdown()
print('ALL PASSED')
"
```
Expected: `PASS: file_send, file_id=...` + `PASS: file content verified`

- [ ] **Step 8: Commit**

```bash
git add chat-software/common.py chat-software/server.py
git commit -m "feat: add file transfer server (port 9998) with upload/download handlers"
```

---

### Task 10: 文件传输 — 客户端发送 UI

**Files:**
- Modify: `chat-software/client.py`

- [ ] **Step 1: 更新 client.py import**

在 client.py 的 `from common import ...` 中添加文件协议常量：

```python
from common import (
    DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE, ENCODING,
    TYPE_REGISTER, TYPE_LOGIN, TYPE_BROADCAST, TYPE_PRIVATE,
    TYPE_GET_USERS, TYPE_SYSTEM, TYPE_RESPONSE,
    TYPE_GET_HISTORY, TYPE_HISTORY,
    TYPE_CREATE_GROUP, TYPE_JOIN_GROUP, TYPE_LEAVE_GROUP,
    TYPE_DELETE_GROUP, TYPE_GROUP_USERS, TYPE_GROUP_MSG,
    TYPE_FILE_SEND, TYPE_FILE_NOTIFY, TYPE_FILE_DOWNLOAD,
    FILE_PORT, FILE_CHUNK,
    STATUS_OK, STATUS_ERROR,
    make_message, parse_message, conversation_key, group_key,
)
```

并添加 `import os` 和 `from tkinter import filedialog`（已有 tkinter，只需加 filedialog）：

在 `from tkinter import messagebox, simpledialog` 行追加 `filedialog`：
```python
from tkinter import messagebox, simpledialog, filedialog
```

- [ ] **Step 2: 添加附件按钮**

在 `_build_right_panel` 中 emoji_btn 右边添加附件按钮（定位到 emoji_btn.pack 行之后）：

```python
        self.attach_btn = tk.Button(self.input_frame, text="📎", width=4,
                                     command=self._send_file, bg=BG_COLOR, fg=BLACK,
                                     font=(FONT_FAMILY, 12), relief=tk.FLAT, cursor="hand2")
        self.attach_btn.pack(side=tk.RIGHT, ipady=2)
```

- [ ] **Step 3: 添加 _send_file 方法**

在 `_show_emoji_panel` 之后插入：

```python
    def _send_file(self):
        """选择文件并发送"""
        filepath = filedialog.askopenfilename(parent=self.root, title="选择文件")
        if not filepath:
            return
        filename = os.path.basename(filepath)
        fsize = os.path.getsize(filepath)

        # 通过聊天通道注册文件
        receiver = self.current_chat if not self.current_chat.startswith("group:") and self.current_chat != "public" else self.username
        try:
            self.socket.sendall(
                make_message(TYPE_FILE_SEND, receiver=receiver, filename=filename, size=fsize).encode(ENCODING)
            )
        except Exception as e:
            self._add_bubble("[系统]", f"发送文件失败: {e}", "")
            return

        # 等待响应获取 file_id（在主 receive 循环中异步处理）
        self._pending_upload = {"filepath": filepath, "filename": filename, "fsize": fsize, "receiver": receiver}
```

**注意**：`_pending_upload` 在 `__init__` 中初始化：
```python
        self._pending_upload = None
```

- [ ] **Step 4: 在 _handle_message 中处理 file_send 响应**

在 `TYPE_RESPONSE` 分支中，检查是否有 `file_id`：

```python
        elif msg_type == TYPE_RESPONSE:
            # 群创建/加入响应
            group_data = msg.get("group")
            if group_data:
                exist = [g for g in self._groups if g['id'] == group_data['id']]
                if not exist:
                    self._groups.append(group_data)
                self._rebuild_conv_list()
                self.root.after(100, lambda gid=group_data['id']: self._switch_to(f"group:{gid}"))
            # 文件发送响应
            file_id = msg.get("file_id")
            if file_id and self._pending_upload:
                self._do_file_upload(file_id, self._pending_upload)
                self._pending_upload = None
```

- [ ] **Step 5: 添加 _do_file_upload 和 _upload_thread 方法**

```python
    def _do_file_upload(self, file_id, info):
        """启动上传线程"""
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
                # 上传完成，本地回显文件卡片
                self._add_bubble("[系统]",
                    f"文件已发送: {info['filename']} ({info['fsize']:,} bytes)", "")
                # 渲染发送方文件卡片
                self.root.after(0, lambda: self._render_file_card(
                    self.username, info["filename"], info["fsize"], file_id, True,
                ))
            except Exception as e:
                self._add_bubble("[系统]", f"上传文件失败: {e}", "")
        threading.Thread(target=upload, daemon=True).start()

    def _render_file_card(self, sender, filename, fsize, file_id, is_sender):
        """渲染文件卡片气泡"""
        is_me = (sender == self.username)
        bubble_bg = GREEN_BUBBLE if is_me else WHITE
        size_str = f"{fsize:,} B" if fsize < 1024 else f"{fsize/1024:.1f} KB"

        outer = tk.Frame(self.bubble_frame, bg=BG_COLOR)
        if is_me:
            outer.pack(anchor="e", pady=1, padx=(40, 6))
        else:
            outer.pack(anchor="w", pady=1, padx=(6, 40))

        inner = tk.Frame(outer, bg=bubble_bg, padx=10, pady=6)
        inner.pack()

        # 文件名
        tk.Label(inner, text=f"📄 {filename}", font=self.bubble_font,
                bg=bubble_bg, fg=BLACK).pack(anchor="w")
        # 文件大小
        tk.Label(inner, text=size_str, font=self.time_font,
                bg=bubble_bg, fg=GRAY).pack(anchor="w")

        # 下载按钮（仅非发送方显示）
        if not is_sender:
            self._file_progress = tk.StringVar(value="下载")
            btn = tk.Button(inner, textvariable=self._file_progress,
                           font=self.time_font, relief=tk.GROOVE, cursor="hand2",
                           command=lambda: self._download_file(file_id, filename))
            btn.pack(pady=(4, 0))
            inner._download_btn = btn

        self._scroll_to_bottom()
```

- [ ] **Step 6: Commit**

```bash
git add chat-software/client.py
git commit -m "feat: add file send UI with attach button, upload thread, and file card"
```

---

### Task 11: 文件传输 — 客户端接收 UI（下载 + 进度）

**Files:**
- Modify: `chat-software/client.py`

- [ ] **Step 1: 添加 _handle_message TYPE_FILE_NOTIFY 处理**

在 `TYPE_GROUP_MSG` 分支之后插入：

```python
        elif msg_type == TYPE_FILE_NOTIFY:
            filename = msg.get("filename", "")
            fsize = msg.get("size", 0)
            file_id = msg.get("file_id", "")
            sender = msg.get("sender", "")
            self.root.after(0, lambda: self._render_file_card(
                sender, filename, fsize, file_id, False,
            ))
```

- [ ] **Step 2: 添加 _download_file 方法**

```python
    def _download_file(self, file_id, filename):
        """启动下载线程"""
        def download():
            self.root.after(0, lambda: self._file_progress.set("下载中..."))
            try:
                fs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                fs.settimeout(30)
                fs.connect((DEFAULT_HOST, FILE_PORT))
                fs.sendall((file_id + "\n").encode(ENCODING))

                os.makedirs("downloads", exist_ok=True)
                save_path = os.path.join("downloads", filename)
                # 避免覆盖
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(save_path):
                    save_path = os.path.join("downloads", f"{base} ({counter}){ext}")
                    counter += 1

                received = 0
                with open(save_path, "wb") as f:
                    while True:
                        chunk = fs.recv(FILE_CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                fs.close()
                self.root.after(0, lambda: self._file_progress.set("已下载 ✓"))
                self._add_bubble("[系统]", f"文件已保存: {save_path}", "")
            except Exception as e:
                self._add_bubble("[系统]", f"下载失败: {e}", "")
                self.root.after(0, lambda: self._file_progress.set("重试"))
        threading.Thread(target=download, daemon=True).start()
```

- [ ] **Step 3: 删除旧 Listbox 相关方法**

删除不再需要的方法：
- `_on_conversation_select`（被 `_on_tree_select` 替代）
- `conv_listbox` 相关初始化代码

**确认 **`refresh_users` 中的请求在线用户逻辑保持不变。

**确认 ** 旧 `_rebuild_conv_list` 中的 `self.conv_listbox` 引用已全部替换为 `self.conv_tree`。

- [ ] **Step 4: Commit**

```bash
git add chat-software/client.py
git commit -m "feat: add file download with progress, file_notify handler"
```

---

### Task 12: 集成测试 + 清理

**Files:**
- (no committed files created)

- [ ] **Step 1: 清理旧文件**

```bash
rm -f D:/moniC/project/jiwang-keshe/chat-software/chat.db D:/moniC/project/jiwang-keshe/chat-software/chat.db-wal D:/moniC/project/jiwang-keshe/chat-software/chat.db-shm
rm -rf D:/moniC/project/jiwang-keshe/chat-software/files
rm -rf D:/moniC/project/jiwang-keshe/chat-software/downloads
```

- [ ] **Step 2: 集成测试脚本**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
import socket, time, threading, os
from server import ChatServer
from common import *

server = ChatServer()
t = threading.Thread(target=server.start, daemon=True); t.start()
time.sleep(0.8)

def client():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(5)
    s.connect(('127.0.0.1', 9999))
    return s

# 1. Alice 注册+登录
s1 = client()
s1.sendall(make_message(TYPE_REGISTER, username='alice', password='123').encode(ENCODING))
assert parse_message(s1.recv(BUFFER_SIZE).decode(ENCODING))['status'] == 'ok'; s1.close()
s1 = client()
s1.sendall(make_message(TYPE_LOGIN, username='alice', password='123').encode(ENCODING))
r = parse_message(s1.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok' and 'groups' in r and r['groups'] == []
print('[PASS] Alice 登录, groups=[]')

# 2. Alice 创建群
s1.sendall(make_message(TYPE_CREATE_GROUP, name='测试群').encode(ENCODING))
r = parse_message(s1.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok'; gid = r['group']['id']
print(f'[PASS] 创建群成功, gid={gid}')

# 3. Bob 注册+登录+加群
s2 = client()
s2.sendall(make_message(TYPE_REGISTER, username='bob', password='456').encode(ENCODING))
parse_message(s2.recv(BUFFER_SIZE).decode(ENCODING)); s2.close()
s2 = client()
s2.sendall(make_message(TYPE_LOGIN, username='bob', password='456').encode(ENCODING))
r = parse_message(s2.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok' and len(r['groups']) == 0
print(f'[PASS] Bob 登录, groups={r[\"groups\"]}')

# Bob 加群
s2.sendall(make_message(TYPE_JOIN_GROUP, group_id=gid).encode(ENCODING))
r = parse_message(s2.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok'
print(f'[PASS] Bob 加入群 {gid}')

# 4. 群消息
s2.sendall(make_message(TYPE_GROUP_MSG, group_id=gid, content='hello group', timestamp=now_iso()).encode(ENCODING))
time.sleep(0.3)
# alice 收到群消息（通过 recv）
s1.settimeout(1)
data = s1.recv(BUFFER_SIZE)
msg = parse_message(data.decode(ENCODING))
assert msg['type'] == TYPE_GROUP_MSG and msg['content'] == 'hello group'
print(f'[PASS] 群消息: {msg[\"sender\"]} → {msg[\"content\"]}')

# 5. 文件传输
s1.sendall(make_message(TYPE_FILE_SEND, receiver='bob', filename='test.txt', size=4).encode(ENCODING))
r = parse_message(s1.recv(BUFFER_SIZE).decode(ENCODING))
fid = r['file_id']
fs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
fs.settimeout(5)
fs.connect(('127.0.0.1', 9998))
fs.sendall((fid + '\n').encode(ENCODING))
fs.sendall(b'data')
fs.close()
time.sleep(0.5)
assert os.path.exists(f'files/{fid}')
print(f'[PASS] 文件上传成功')

# Bob 应收到 file_notify
s2.settimeout(2)
data = s2.recv(BUFFER_SIZE)
fn = parse_message(data.decode(ENCODING))
assert fn['type'] == TYPE_FILE_NOTIFY
assert fn['filename'] == 'test.txt'
print(f'[PASS] Bob 收到文件通知: {fn[\"filename\"]}')

s1.close(); s2.close()
server.shutdown()
print('\n' + '=' * 50)
print('  全部集成测试通过!')
print('=' * 50)
"
```
Expected: 6 个 `[PASS]`

- [ ] **Step 3: 清理测试数据**

```bash
rm -f D:/moniC/project/jiwang-keshe/chat-software/chat.db D:/moniC/project/jiwang-keshe/chat-software/chat.db-wal D:/moniC/project/jiwang-keshe/chat-software/chat.db-shm
rm -rf D:/moniC/project/jiwang-keshe/chat-software/files
rm -rf D:/moniC/project/jiwang-keshe/chat-software/downloads
```

- [ ] **Step 4: Commit**

```bash
git add chat-software/
git commit -m "test: integration test for emoji + group chat + file transfer"
```

---

## Self-Review

1. **Spec coverage:**
   - Emoji 面板（54 emoji, 6x9 grid, 弹出定位） → Task 1-2
   - 群聊：创建/加入/退出/解散群 → Task 4
   - 群聊：groups/group_members 表 → Task 3
   - 群聊：左侧 Treeview 面板（群+联系人） → Task 6
   - 群聊：创建群弹窗+右键菜单 → Task 7
   - 群聊：登录返回 groups → Task 5
   - 群聊：群消息收发 → Task 4 (server) + Task 8 (client)
   - 群聊：群历史兼容 group:xxx key → Task 5
   - 文件传输：文件端口 9998 → Task 9
   - 文件传输：files 表 → Task 9
   - 文件传输：file_send/file_notify/file_download → Task 9-11
   - 文件传输：附件按钮+文件卡片+下载进度 → Task 10-11

2. **Placeholder scan:** 无 TBD/TODO

3. **Type consistency:** `group_key()` 返回 `"group:3"` 格式，在 handler 和 client 中一致使用。`_handle_get_history` 的 target 转换逻辑对所有三种 chat_key 格式正确（public / alice:bob / group:3）。
