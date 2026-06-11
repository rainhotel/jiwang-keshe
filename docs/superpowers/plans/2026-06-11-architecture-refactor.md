# Architecture Refactoring Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split 3 monolithic files (client.py ~1200L, server.py ~1000L, common.py ~100L) into 15 focused modules across `common/`, `server/`, `client/`, `client/ui/` directories.

**Architecture:** Three-layer structure — shared protocol layer (`common/`), server layer (`server/` with database + handlers + network), client layer (`client/` with network + ui components). All imports use package-relative paths from `chat-software/`.

**Tech Stack:** Python 3.6+, tkinter, Pillow, sqlite3, socket

---

## File Map

| New File | From | Contents |
|----------|------|----------|
| `common/__init__.py` | new | Re-exports from protocol |
| `common/protocol.py` | `common.py` | All constants, make_message, parse_message, helpers |
| `server/__init__.py` | new | Empty |
| `server/database.py` | `server.py` | SQLite: tables, CRUD for all entities |
| `server/handlers.py` | `server.py` | Message handler functions |
| `server/server.py` | `server.py` | TCP, dispatch, file transfer, state mgmt |
| `server/main.py` | `server.py:837-839` | Entry point |
| `client/__init__.py` | new | Empty |
| `client/network.py` | `client.py` | Socket connect/send/recv, callback dispatch |
| `client/ui/__init__.py` | new | Empty |
| `client/ui/login.py` | `client.py` | LoginWindow class |
| `client/ui/chat.py` | `client.py` | ChatWindow class |
| `client/ui/widgets.py` | `client.py` | Bubbles, file cards, image previews |
| `client/ui/dialogs.py` | `client.py` | Search, add member, emoji, group dialogs |
| `client/ui/viewer.py` | `client.py` | Image viewer Toplevel |
| `client/main.py` | `client.py:986-998` | Entry point |

**Files to delete after migration:** `client.py`, `server.py`, `common.py`
**Files kept:** `requirements.txt`, `messages.json`, `users.json`

---

### Task 1: Create directory structure and `common/protocol.py`

**Files:**
- Create: `chat-software/common/__init__.py`
- Create: `chat-software/common/protocol.py`
- Create: `chat-software/server/__init__.py`
- Create: `chat-software/client/__init__.py`
- Create: `chat-software/client/ui/__init__.py`
- Modify: `chat-software/common.py` → delete after verifying

- [ ] **Step 1: Create all directories**

```bash
mkdir -p chat-software/common chat-software/server chat-software/client/ui
```

- [ ] **Step 2: Create `common/__init__.py`**

```python
from common.protocol import *
```

- [ ] **Step 3: Create `common/protocol.py`** — move entire content of `common.py`, adjusting import for `datetime`:

```python
"""
公共模块：协议常量、消息序列化/反序列化
"""

import json
from datetime import datetime, timezone

# === 消息类型常量 ===
TYPE_REGISTER = "register"
TYPE_LOGIN = "login"
TYPE_BROADCAST = "broadcast"
TYPE_PRIVATE = "private"
TYPE_GET_USERS = "get_users"
TYPE_SYSTEM = "system"
TYPE_RESPONSE = "response"

# === 响应状态码 ===
STATUS_OK = "ok"
STATUS_ERROR = "error"

# === 服务器配置 ===
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9999

# === 缓冲区大小 ===
BUFFER_SIZE = 4096

# === 编码 ===
ENCODING = "utf-8"


def make_message(msg_type, **kwargs):
    """构造一条JSON消息"""
    msg = {"type": msg_type}
    msg.update(kwargs)
    return json.dumps(msg, ensure_ascii=False)


def parse_message(data):
    """解析一条JSON消息，返回dict；解析失败返回None"""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None


def make_response(status, message=""):
    """构造响应消息"""
    return make_message(TYPE_RESPONSE, status=status, message=message)


def make_system_msg(content):
    """构系统广播消息"""
    return make_message(TYPE_BROADCAST, content=content, sender="[系统]")


# === 历史消息相关常量 ===
TYPE_GET_HISTORY = "get_history"
TYPE_HISTORY = "history"

MAX_HISTORY = 50
MAX_MESSAGES_PER_CHAT = 500


def now_iso():
    """返回当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()


def conversation_key(user1, user2):
    """私聊会话的唯一 key"""
    a, b = (user1, user2) if user1 < user2 else (user2, user1)
    return f"{a}:{b}"


def group_key(group_id):
    """群聊 chat_key"""
    return f"group:{group_id}"


# === 群聊相关常量 ===
TYPE_CREATE_GROUP = "create_group"
TYPE_JOIN_GROUP = "join_group"
TYPE_LEAVE_GROUP = "leave_group"
TYPE_DELETE_GROUP = "delete_group"
TYPE_GROUP_USERS = "group_users"
TYPE_GROUP_MSG = "group_msg"

# === 文件传输相关常量 ===
TYPE_FILE_SEND = "file_send"
TYPE_FILE_NOTIFY = "file_notify"
TYPE_FILE_DOWNLOAD = "file_download"
TYPE_ADD_MEMBER = "add_member"
TYPE_SEARCH_USERS = "search_users"
TYPE_ADD_CONTACT = "add_contact"

FILE_PORT = 9998
FILE_CHUNK = 65536
```

- [ ] **Step 4: Verify** — `python -c "from common.protocol import make_message; print(make_message('test', x=1))"` should output valid JSON

---

### Task 2: Create `server/database.py`

**Files:**
- Create: `chat-software/server/database.py`

- [ ] **Step 1: Write `server/database.py`**

```python
"""
数据库层：SQLite 连接管理、建表、所有 CRUD 操作
"""

import sqlite3
import os

from common.protocol import MAX_MESSAGES_PER_CHAT

DB_FILE = "chat.db"


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        os.makedirs("files", exist_ok=True)

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username   TEXT PRIMARY KEY,
                password   TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_key  TEXT NOT NULL,
                sender    TEXT NOT NULL,
                content   TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat
            ON messages(chat_key, id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
            ON messages(chat_key, timestamp)
        """)
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
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                username TEXT,
                contact  TEXT,
                added_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (username, contact)
            )
        """)
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
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ========================
    #  Users
    # ========================
    def load_users(self):
        rows = self.conn.execute("SELECT username, password FROM users").fetchall()
        return {r[0]: r[1] for r in rows}

    def register_user(self, username, password):
        self.conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, password),
        )
        self.conn.commit()

    def search_users(self, query, exclude):
        rows = self.conn.execute(
            "SELECT username FROM users WHERE username LIKE ? AND username != ? LIMIT 20",
            (f"%{query}%", exclude),
        ).fetchall()
        return [r[0] for r in rows]

    # ========================
    #  Messages
    # ========================
    def add_message(self, chat_key, sender, content, timestamp):
        self.conn.execute(
            "INSERT INTO messages (chat_key, sender, content, timestamp) VALUES (?, ?, ?, ?)",
            (chat_key, sender, content, timestamp),
        )
        self.conn.execute("""
            DELETE FROM messages WHERE chat_key = ? AND id NOT IN (
                SELECT id FROM messages WHERE chat_key = ? ORDER BY id DESC LIMIT ?
            )
        """, (chat_key, chat_key, MAX_MESSAGES_PER_CHAT))
        self.conn.commit()

    def get_history(self, chat_key, limit=50):
        rows = self.conn.execute(
            "SELECT sender, content, timestamp FROM messages "
            "WHERE chat_key = ? ORDER BY id DESC LIMIT ?",
            (chat_key, limit),
        ).fetchall()
        return [{"sender": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]

    def get_conversations(self, username):
        rows = self.conn.execute(
            "SELECT DISTINCT chat_key FROM messages WHERE chat_key != 'public'"
        ).fetchall()
        partners = []
        for (key,) in rows:
            users = key.split(":")
            if username in users:
                partner = users[0] if users[1] == username else users[1]
                last = self.conn.execute(
                    "SELECT timestamp FROM messages WHERE chat_key = ? ORDER BY id DESC LIMIT 1",
                    (key,),
                ).fetchone()
                partners.append((partner, last[0] if last else ""))
        partners.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in partners]

    # ========================
    #  Groups
    # ========================
    def create_group(self, name, created_by):
        cur = self.conn.execute(
            "INSERT INTO groups (name, created_by) VALUES (?, ?)", (name, created_by)
        )
        gid = cur.lastrowid
        self.conn.execute(
            "INSERT INTO group_members (group_id, username) VALUES (?, ?)", (gid, created_by)
        )
        self.conn.commit()
        return gid

    def join_group(self, gid, username):
        self.conn.execute(
            "INSERT INTO group_members (group_id, username) VALUES (?, ?)", (gid, username)
        )
        self.conn.commit()

    def leave_group(self, gid, username):
        self.conn.execute(
            "DELETE FROM group_members WHERE group_id=? AND username=?", (gid, username)
        )
        self.conn.commit()

    def delete_group(self, gid):
        self.conn.execute("DELETE FROM group_members WHERE group_id=?", (gid,))
        self.conn.execute("DELETE FROM groups WHERE id=?", (gid,))
        self.conn.commit()

    def is_group_member(self, gid, username):
        row = self.conn.execute(
            "SELECT 1 FROM group_members WHERE group_id=? AND username=?", (gid, username)
        ).fetchone()
        return row is not None

    def get_group_info(self, gid):
        return self.conn.execute(
            "SELECT id, name, created_by FROM groups WHERE id=?", (gid,)
        ).fetchone()

    def get_group_members(self, gid):
        rows = self.conn.execute(
            "SELECT username FROM group_members WHERE group_id=?", (gid,)
        ).fetchall()
        return [r[0] for r in rows]

    def get_user_groups(self, username):
        gids = self.conn.execute(
            "SELECT group_id FROM group_members WHERE username=?", (username,)
        ).fetchall()
        groups = []
        for (gid,) in gids:
            grp = self.get_group_info(gid)
            if grp:
                groups.append({
                    "id": grp[0], "name": grp[1], "created_by": grp[2],
                    "members": self.get_group_members(gid),
                })
        return groups

    # ========================
    #  Files
    # ========================
    def insert_file(self, file_id, filename, size, sender, receiver, chat_key):
        self.conn.execute(
            "INSERT INTO files (file_id, filename, size, sender, receiver, chat_key) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, filename, size, sender, receiver, chat_key),
        )
        self.conn.commit()

    def update_file_size(self, file_id, size):
        self.conn.execute("UPDATE files SET size=? WHERE file_id=?", (size, file_id))
        self.conn.commit()

    def get_file_info(self, file_id):
        return self.conn.execute(
            "SELECT receiver, filename, size, sender, chat_key FROM files WHERE file_id=?",
            (file_id,),
        ).fetchone()

    # ========================
    #  Contacts
    # ========================
    def get_contacts(self, username):
        rows = self.conn.execute(
            "SELECT contact FROM contacts WHERE username=? ORDER BY added_at", (username,)
        ).fetchall()
        return [r[0] for r in rows]

    def add_contact(self, username, contact):
        exist = self.conn.execute(
            "SELECT 1 FROM contacts WHERE username=? AND contact=?", (username, contact)
        ).fetchone()
        if exist:
            return False
        self.conn.execute(
            "INSERT INTO contacts (username, contact) VALUES (?, ?)", (username, contact)
        )
        self.conn.commit()
        return True
```

---

### Task 3: Create `server/handlers.py`

**Files:**
- Create: `chat-software/server/handlers.py`

- [ ] **Step 1: Write `server/handlers.py`** — each handler is a standalone function:

```python
"""
消息处理器：每个函数处理一种消息类型
签名: handler(msg, sock, server_state, db) → new_username (仅 login 返回, 其他返回 None)
"""

from common.protocol import (
    TYPE_REGISTER, TYPE_LOGIN, TYPE_BROADCAST, TYPE_PRIVATE,
    TYPE_GET_USERS, TYPE_RESPONSE, TYPE_SYSTEM,
    TYPE_GET_HISTORY, TYPE_HISTORY,
    TYPE_CREATE_GROUP, TYPE_JOIN_GROUP, TYPE_ADD_MEMBER,
    TYPE_LEAVE_GROUP, TYPE_DELETE_GROUP, TYPE_GROUP_USERS, TYPE_GROUP_MSG,
    TYPE_FILE_SEND, TYPE_FILE_NOTIFY, TYPE_FILE_DOWNLOAD,
    TYPE_SEARCH_USERS, TYPE_ADD_CONTACT,
    MAX_HISTORY,
    STATUS_OK, STATUS_ERROR,
    make_message, make_response, make_system_msg,
    now_iso, conversation_key, group_key,
)


def handle_register(msg, sock, server, db):
    username = msg.get("username", "").strip()
    password = msg.get("password", "").strip()
    if not username or not password:
        server._safe_send(sock, make_response(STATUS_ERROR, "用户名和密码不能为空").encode())
        return None
    with server.lock:
        if username in server.clients:
            server._safe_send(sock, make_response(STATUS_ERROR, "用户名已存在").encode())
            return None
        db.register_user(username, password)
        server.clients[username] = {"password": password, "addr": None, "socket": None}
    server._safe_send(sock, make_response(STATUS_OK, "注册成功").encode())
    return None


def handle_login(msg, sock, server, db):
    username = msg.get("username", "").strip()
    password = msg.get("password", "").strip()
    if not username or not password:
        server._safe_send(sock, make_response(STATUS_ERROR, "用户名和密码不能为空").encode())
        return None
    with server.lock:
        if username not in server.clients:
            server._safe_send(sock, make_response(STATUS_ERROR, "用户不存在，请先注册").encode())
            return None
        stored_pw = server.clients[username].get("password")
        if stored_pw is not None and stored_pw != password:
            server._safe_send(sock, make_response(STATUS_ERROR, "密码错误").encode())
            return None
        if server.clients[username].get("addr") is not None:
            server._safe_send(sock, make_response(STATUS_ERROR, "该用户已在线").encode())
            return None
        server.clients[username]["addr"] = addr = msg.get("_addr")  # set by dispatch
        server.clients[username]["socket"] = sock

    public_history = db.get_history("public", MAX_HISTORY)
    conversations = db.get_conversations(username)
    groups = db.get_user_groups(username)
    contacts = db.get_contacts(username)
    login_resp = make_message(
        TYPE_RESPONSE, status=STATUS_OK, message="登录成功",
        public_history=public_history, conversations=conversations, groups=groups,
        contacts=contacts,
    )
    server._safe_send(sock, login_resp.encode())
    server.broadcast(f"{username} 加入了聊天室", system=True, exclude=username)
    return username


def handle_broadcast(msg, sock, server, db):
    content = msg.get("content", "")
    if not content.strip():
        return None
    username = server._current_user(sock)
    if not username:
        server._safe_send(sock, make_response(STATUS_ERROR, "请先登录").encode())
        return None
    ts = now_iso()
    db.add_message("public", username, content, ts)
    full_msg = make_message(TYPE_BROADCAST, content=content, sender=username, timestamp=ts)
    server.broadcast(full_msg, exclude=username)
    return None


def handle_private(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        server._safe_send(sock, make_response(STATUS_ERROR, "请先登录").encode())
        return None
    target = msg.get("target", "").strip()
    content = msg.get("content", "")
    if not target or not content.strip():
        server._safe_send(sock, make_response(STATUS_ERROR, "私聊格式: @用户名 消息").encode())
        return None
    with server.lock:
        if target not in server.clients or server.clients[target].get("addr") is None:
            server._safe_send(sock, make_response(STATUS_ERROR, f"用户 '{target}' 不在线").encode())
            return None
    key = conversation_key(username, target)
    ts = now_iso()
    db.add_message(key, username, content, ts)

    target_msg = make_message(TYPE_PRIVATE, content=content, sender=username, target=target)
    server._safe_send(server.clients[target]["socket"], target_msg.encode())

    echo = make_message(TYPE_PRIVATE, content=content, sender=username, target=target, timestamp=ts)
    server._safe_send(sock, echo.encode())
    return None


def handle_get_users(msg, sock, server, db):
    with server.lock:
        online = [u for u, info in server.clients.items() if info.get("addr") is not None]
    server._safe_send(sock, make_message(TYPE_GET_USERS, users=online).encode())
    return None


def handle_get_history(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    target = msg.get("target", "public")
    if target != "public" and not target.startswith("group:"):
        target = conversation_key(username, target)
    msgs = db.get_history(target, MAX_HISTORY)
    server._safe_send(sock, make_message(TYPE_HISTORY, target=target, messages=msgs).encode())
    return None


def handle_create_group(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    name = msg.get("name", "").strip()
    if not name:
        server._safe_send(sock, make_response(STATUS_ERROR, "群名不能为空").encode())
        return None
    gid = db.create_group(name, username)
    server._safe_send(sock, make_message(
        TYPE_RESPONSE, status=STATUS_OK, message="群创建成功",
        group={"id": gid, "name": name, "created_by": username},
    ).encode())
    return None


def handle_join_group(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    gid = msg.get("group_id")
    if not gid:
        return None
    grp = db.get_group_info(gid)
    if not grp:
        server._safe_send(sock, make_response(STATUS_ERROR, "群不存在").encode())
        return None
    if db.is_group_member(gid, username):
        server._safe_send(sock, make_response(STATUS_ERROR, "你已在该群中").encode())
        return None
    db.join_group(gid, username)
    gname = grp[1]
    server._safe_send(sock, make_message(
        TYPE_RESPONSE, status=STATUS_OK, message=f"已加入群 '{gname}'",
        group={"id": gid, "name": gname},
    ).encode())
    return None


def handle_add_member(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    gid = msg.get("group_id")
    target = msg.get("target", "").strip()
    if not gid or not target:
        server._safe_send(sock, make_response(STATUS_ERROR, "参数不完整").encode())
        return None
    if target == username:
        server._safe_send(sock, make_response(STATUS_ERROR, "不能添加自己").encode())
        return None
    with server.lock:
        if not db.is_group_member(gid, username):
            server._safe_send(sock, make_response(STATUS_ERROR, "你不是该群成员").encode())
            return None
        if db.is_group_member(gid, target):
            server._safe_send(sock, make_response(STATUS_ERROR, f"'{target}' 已在该群中").encode())
            return None
        if target not in server.clients:
            server._safe_send(sock, make_response(STATUS_ERROR, f"用户 '{target}' 不存在").encode())
            return None
        db.join_group(gid, target)
    grp = db.get_group_info(gid)
    gname = grp[1] if grp else ""
    server._safe_send(sock, make_message(
        TYPE_RESPONSE, status=STATUS_OK,
        message=f"已将 '{target}' 加入群 '{gname}'",
        group={"id": gid, "name": gname},
    ).encode())
    target_info = server.clients.get(target)
    if target_info and target_info.get("socket"):
        server._safe_send(target_info["socket"], make_message(
            TYPE_RESPONSE, status=STATUS_OK,
            message=f"{username} 将你加入了群 '{gname}'",
            group={"id": gid, "name": gname},
        ).encode())
    return None


def handle_leave_group(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    gid = msg.get("group_id")
    if not gid:
        return None
    db.leave_group(gid, username)
    server._safe_send(sock, make_response(STATUS_OK, "已退出群").encode())
    return None


def handle_delete_group(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    gid = msg.get("group_id")
    if not gid:
        return None
    grp = db.get_group_info(gid)
    if not grp:
        server._safe_send(sock, make_response(STATUS_ERROR, "群不存在").encode())
        return None
    if grp[2] != username:
        server._safe_send(sock, make_response(STATUS_ERROR, "只有群创建者可以解散群").encode())
        return None
    db.delete_group(gid)
    server._safe_send(sock, make_response(STATUS_OK, "群已解散").encode())
    return None


def handle_group_users(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    gid = msg.get("group_id")
    if not gid:
        return None
    members = db.get_group_members(gid)
    server._safe_send(sock, make_message(TYPE_GROUP_USERS, group_id=gid, users=members).encode())
    return None


def handle_group_msg(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    gid = msg.get("group_id")
    content = msg.get("content", "")
    if not gid or not content.strip():
        return None
    if not db.is_group_member(gid, username):
        server._safe_send(sock, make_response(STATUS_ERROR, "你不是该群成员").encode())
        return None
    key = group_key(gid)
    ts = now_iso()
    db.add_message(key, username, content, ts)
    full_msg = make_message(TYPE_GROUP_MSG, group_id=gid, content=content, sender=username, timestamp=ts)
    data = full_msg.encode()
    members = db.get_group_members(gid)
    with server.lock:
        for uname in members:
            info = server.clients.get(uname)
            if info and info.get("socket"):
                try:
                    server._safe_send(info["socket"], data)
                except Exception:
                    pass
    return None


def handle_file_send(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    receiver = msg.get("receiver", "").strip()
    filename = msg.get("filename", "").strip()
    size = msg.get("size", 0)
    if not receiver or not filename:
        server._safe_send(sock, make_response(STATUS_ERROR, "参数不完整").encode())
        return None
    import uuid
    file_id = str(uuid.uuid4())
    chat_key = conversation_key(username, receiver) if receiver != username else "public"
    db.insert_file(file_id, filename, size, username, receiver, chat_key)
    server._safe_send(sock, make_message(TYPE_RESPONSE, status=STATUS_OK, file_id=file_id).encode())
    return None


def handle_file_download(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    file_id = msg.get("file_id", "")
    if not file_id:
        return None
    row = db.get_file_info(file_id)
    if not row:
        server._safe_send(sock, make_response(STATUS_ERROR, "文件不存在").encode())
        return None
    server._safe_send(sock, make_message(TYPE_RESPONSE, status=STATUS_OK, file_id=file_id).encode())
    return None


def handle_search_users(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    query = msg.get("query", "").strip()
    if not query:
        server._safe_send(sock, make_message(TYPE_SEARCH_USERS, users=[]).encode())
        return None
    users = db.search_users(query, username)
    server._safe_send(sock, make_message(TYPE_SEARCH_USERS, users=users).encode())
    return None


def handle_add_contact(msg, sock, server, db):
    username = server._current_user(sock)
    if not username:
        return None
    target = msg.get("username", "").strip()
    if not target or target == username:
        server._safe_send(sock, make_response(STATUS_ERROR, "参数无效").encode())
        return None
    with server.lock:
        if target not in server.clients:
            server._safe_send(sock, make_response(STATUS_ERROR, "用户不存在").encode())
            return None
        if not db.add_contact(username, target):
            server._safe_send(sock, make_response(STATUS_ERROR, "已在好友列表中").encode())
            return None
    server._safe_send(sock, make_message(
        TYPE_RESPONSE, status=STATUS_OK,
        message=f"已添加 '{target}' 为好友", contact=target,
    ).encode())
    return None


# 消息类型 → handler 映射
HANDLERS = {
    TYPE_REGISTER: handle_register,
    TYPE_LOGIN: handle_login,
    TYPE_BROADCAST: handle_broadcast,
    TYPE_PRIVATE: handle_private,
    TYPE_GET_USERS: handle_get_users,
    TYPE_GET_HISTORY: handle_get_history,
    TYPE_CREATE_GROUP: handle_create_group,
    TYPE_JOIN_GROUP: handle_join_group,
    TYPE_ADD_MEMBER: handle_add_member,
    TYPE_LEAVE_GROUP: handle_leave_group,
    TYPE_DELETE_GROUP: handle_delete_group,
    TYPE_GROUP_USERS: handle_group_users,
    TYPE_GROUP_MSG: handle_group_msg,
    TYPE_FILE_SEND: handle_file_send,
    TYPE_FILE_DOWNLOAD: handle_file_download,
    TYPE_SEARCH_USERS: handle_search_users,
    TYPE_ADD_CONTACT: handle_add_contact,
}
```

---

### Task 4: Create `server/server.py`

**Files:**
- Create: `chat-software/server/server.py`

- [ ] **Step 1: Write `server/server.py`** — core Server class with networking:

```python
"""
服务端核心：TCP 连接管理、消息分派、文件传输
"""

import socket
import threading
import json
import os
import time
import uuid

from common.protocol import (
    DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE, ENCODING,
    TYPE_RESPONSE, TYPE_FILE_NOTIFY, TYPE_SYSTEM,
    FILE_PORT, FILE_CHUNK,
    STATUS_ERROR,
    make_message, make_response, make_system_msg, parse_message,
)

from server.handlers import HANDLERS


def _ts():
    return time.strftime("[%H:%M:%S]")


class Server:
    def __init__(self, db):
        self.host = DEFAULT_HOST
        self.port = DEFAULT_PORT
        self.db = db
        self.server_socket = None
        self.clients = {}  # {username: {"password": str, "addr": tuple, "socket": socket}}
        self.lock = threading.RLock()
        self.send_lock = threading.Lock()
        # 加载已注册用户
        users = db.load_users()
        for username, password in users.items():
            self.clients[username] = {"password": password, "addr": None, "socket": None}
        print(f"[服务器] 已加载 {len(users)} 个已注册用户")
        # socket → username 映射
        self._sock_user = {}

    def _current_user(self, sock):
        return self._sock_user.get(sock)

    def _set_current_user(self, sock, username):
        if username:
            self._sock_user[sock] = username

    def _safe_send(self, sock, data):
        """线程安全的 socket 发送，防止多线程并发写入导致数据交错"""
        with self.send_lock:
            sock.sendall(data)

    def broadcast(self, content, system=False, exclude=None):
        if system:
            msg = make_system_msg(content)
        else:
            msg = content
        data = msg.encode(ENCODING)
        with self.lock:
            for u, info in list(self.clients.items()):
                if u == exclude:
                    continue
                sock = info.get("socket")
                if sock:
                    try:
                        self._safe_send(sock, data)
                    except Exception:
                        pass

    def _notify_file_to_public(self, data, sender):
        with self.lock:
            for u, info in self.clients.items():
                if u == sender:
                    continue
                if info.get("socket"):
                    try:
                        self._safe_send(info["socket"], data)
                    except Exception:
                        pass

    def _notify_file_to_group(self, data, gid, sender):
        rows = self.db.conn.execute(
            "SELECT username FROM group_members WHERE group_id=?", (gid,)
        ).fetchall()
        with self.lock:
            for (uname,) in rows:
                if uname == sender:
                    continue
                info = self.clients.get(uname)
                if info and info.get("socket"):
                    try:
                        self._safe_send(info["socket"], data)
                    except Exception:
                        pass

    def _notify_file_to_user(self, data, receiver):
        with self.lock:
            info = self.clients.get(receiver)
            if info and info.get("socket"):
                try:
                    self._safe_send(info["socket"], data)
                except Exception:
                    pass

    def _handle_file_conn(self, client, addr):
        try:
            header = b""
            while b"\n" not in header:
                chunk = client.recv(128)
                if not chunk:
                    return
                header += chunk
            idx = header.index(b"\n")
            file_id = header[:idx].decode(ENCODING).strip()
            rest = header[idx + 1:]
            rest_data = [rest] if rest else []

            filepath = os.path.join("files", file_id)
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    while True:
                        chunk = f.read(FILE_CHUNK)
                        if not chunk:
                            break
                        client.sendall(chunk)
                print(f"[文件] 下载完成: {filepath} → {addr}")
            else:
                received_size = 0
                with open(filepath, "wb") as f:
                    for buf in rest_data:
                        if buf:
                            f.write(buf)
                            received_size += len(buf)
                    while True:
                        chunk = client.recv(FILE_CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        received_size += len(chunk)
                self.db.update_file_size(file_id, received_size)
                print(f"[文件] 上传完成: {filepath} ({received_size} bytes)")

                row = self.db.get_file_info(file_id)
                if row:
                    _, filename, fsize, sender, chat_key = row
                    notify_data = make_message(
                        TYPE_FILE_NOTIFY, file_id=file_id, filename=filename,
                        size=fsize, sender=sender,
                    ).encode(ENCODING)
                    if chat_key == "public":
                        self._notify_file_to_public(notify_data, sender)
                    elif chat_key.startswith("group:"):
                        gid = int(chat_key.split(":", 1)[1])
                        self._notify_file_to_group(notify_data, gid, sender)
                    else:
                        self._notify_file_to_user(notify_data, row[0])
        except Exception as e:
            print(f"[文件] 连接错误: {e}")
        finally:
            client.close()

    def _start_file_server(self):
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

    def handle_client(self, client_socket, addr):
        username = None
        buffer = ""
        decoder = json.JSONDecoder()

        try:
            while True:
                data = client_socket.recv(BUFFER_SIZE)
                if not data:
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
                    except json.JSONDecodeError:
                        break

                    msg_type = obj.get("type")
                    handler = HANDLERS.get(msg_type)
                    if handler:
                        result = handler(obj, client_socket, self, self.db)
                        if msg_type == "login" and result:
                            username = result
                            self._set_current_user(client_socket, username)
                        elif msg_type == "register":
                            pass  # username stays None
                    else:
                        self._safe_send(client_socket,
                            make_response(STATUS_ERROR, f"未知消息类型: {msg_type}").encode(ENCODING)
                        )
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            if username:
                with self.lock:
                    if username in self.clients:
                        self.clients[username]["addr"] = None
                        self.clients[username]["socket"] = None
                self.broadcast(f"{username} 离开了聊天室", system=True, exclude=username)
            try:
                client_socket.close()
            except Exception:
                pass

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(50)
        self.server_socket.settimeout(1.0)
        print(f"[服务器] 聊天服务器启动成功：{self.host}:{self.port}")
        file_thread = threading.Thread(target=self._start_file_server, daemon=True)
        file_thread.start()
        print(f"[服务器] 文件传输端口: {self.host}:{FILE_PORT}")
        print("[服务器] 等待客户端连接...")

        try:
            while True:
                try:
                    client_socket, addr = self.server_socket.accept()
                    print(f"[服务器] 新连接来自 {addr}")
                    threading.Thread(
                        target=self.handle_client, args=(client_socket, addr), daemon=True
                    ).start()
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            print("\n[服务器] 服务器正在关闭...")
        finally:
            self.shutdown()

    def shutdown(self):
        with self.lock:
            for u, info in self.clients.items():
                if info.get("addr"):
                    try:
                        sock = info.get("socket")
                        if sock:
                            self._safe_send(sock, make_system_msg("服务器已关闭，再见！").encode(ENCODING))
                    except Exception:
                        pass
        if self.server_socket:
            self.server_socket.close()
        self.db.close()
        print("[服务器] 服务器已关闭")
```

---

### Task 5: Create `server/main.py`

**Files:**
- Create: `chat-software/server/main.py`

```python
"""聊天服务端入口"""
from server.database import Database
from server.server import Server

if __name__ == "__main__":
    db = Database()
    srv = Server(db)
    srv.start()
```

---

### Task 6–10: Client-side files

Due to the complexity of splitting the client (1200 lines into 6 files), these will be implemented as separate sub-tasks. The key interfaces are:

**`client/network.py`** — `NetworkClient` class extracting all socket operations
**`client/ui/login.py`** — `LoginWindow` using `NetworkClient`
**`client/ui/chat.py`** — `ChatWindow` using `NetworkClient`, composing widgets
**`client/ui/widgets.py`** — Bubble rendering, file card, image preview helpers
**`client/ui/dialogs.py`** — All dialog popups extracted
**`client/ui/viewer.py`** — Standalone image viewer
**`client/main.py`** — Entry point wiring

These will be created in Tasks 6-11.

---

### Verification

After all tasks complete:

```bash
cd chat-software
python -m py_compile common/protocol.py server/database.py server/handlers.py server/server.py server/main.py
python server/main.py  # Start server, verify it starts without errors
```

Toggle between starting with `python server/main.py` (new) and the old `python server.py` (old, for comparison).
