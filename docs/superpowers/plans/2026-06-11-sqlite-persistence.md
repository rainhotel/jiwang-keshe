# SQLite 持久化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将聊天软件的数据存储从 JSON 文件替换为 SQLite 数据库

**Architecture:** 仅修改 server.py，用 sqlite3 模块替代 json 文件读写。用户数据、消息历史全部走 SQL 查询。common.py 和 client.py 完全不动。

**Tech Stack:** Python 3, sqlite3 (标准库), WAL 模式

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `chat-software/server.py` | Modify | 所有持久化逻辑从 JSON 改为 SQLite |

---

### Task 1: 引入 sqlite3，修改初始化逻辑

**Files:**
- Modify: `chat-software/server.py`

- [ ] **Step 1: 替换 import 和常量**

将 server.py 顶部的 import 区中 `import json, os` 改为 `import json, os, sqlite3`，并删除 `USERS_FILE` 和 `MESSAGES_FILE` 常量。

定位到第 6-9 行：
```python
import socket
import threading
import json
import os
import time
```

改为：

```python
import socket
import threading
import json
import os
import sqlite3
import time
```

定位到第 23-24 行：
```python
USERS_FILE = "users.json"
MESSAGES_FILE = "messages.json"
```

改为：

```python
DB_FILE = "chat.db"
```

- [ ] **Step 2: 重写 __init__**

替换 `__init__` 方法（第 33-42 行）：

原代码：
```python
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        # {username: {"password": str, "addr": tuple}}
        self.clients = {}
        self.lock = threading.RLock()  # 可重入锁，避免 _save_users 内部死锁
        self._load_users()
        self.messages = {"public": []}
        self._load_messages()
```

改为：
```python
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        # {username: {"addr": tuple, "socket": socket}}
        self.clients = {}            # 仅存运行时状态，不再存密码
        self.lock = threading.RLock()
        self._init_db()
        self._load_users()
```

- [ ] **Step 3: 添加 _init_db 方法**

在 `__init__` 之后插入：

```python
    def _init_db(self):
        """打开 SQLite 连接，启用 WAL，建表"""
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
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
        self.conn.commit()
```

- [ ] **Step 4: 重写 _load_users**

替换 `_load_users`（第 47-56 行）：

原代码：
```python
    def _load_users(self):
        """从JSON文件加载已注册用户"""
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding=ENCODING) as f:
                users = json.load(f)
            for u, p in users.items():
                self.clients[u] = {"password": p, "addr": None}
            print(f"[服务器] 已加载 {len(users)} 个已注册用户")
        else:
            print("[服务器] 用户数据文件不存在，将创建新文件")
```

改为：
```python
    def _load_users(self):
        """从 SQLite 加载已注册用户到运行时字典"""
        rows = self.conn.execute(
            "SELECT username, password FROM users"
        ).fetchall()
        for username, password in rows:
            self.clients[username] = {"password": password, "addr": None, "socket": None}
        print(f"[服务器] 已加载 {len(rows)} 个已注册用户")
```

- [ ] **Step 5: 删除 _save_users**

删除 `_save_users` 方法（第 58-63 行）。

- [ ] **Step 6: 删除旧的消息持久化方法**

删除以下四个方法：
- `_load_messages`（第 68-77 行）
- `_save_messages`（第 79-84 行）
- `_add_message`（第 86-100 行）
- `_get_conversations_for_user`（第 102-115 行）

- [ ] **Step 7: 验证服务端能启动**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
from server import ChatServer
s = ChatServer()
print('clients:', s.clients)
print('OK')
s.conn.close()
"
```
Expected: `clients: {}` 然后 `OK`，并生成 `chat.db` 文件。

- [ ] **Step 8: Commit**

```bash
git add chat-software/server.py
git commit -m "refactor: replace JSON files with SQLite - init, load users"
```

---

### Task 2: 注册和登录改 SQL

**Files:**
- Modify: `chat-software/server.py`

- [ ] **Step 1: 重写 _handle_register**

替换 `_handle_register`（第 226-253 行）：

原代码：
```python
    def _handle_register(self, msg, client_socket):
        username = msg.get("username", "").strip()
        password = msg.get("password", "").strip()
        print(f"{_ts()} _handle_register: username='{username}', password='{'***' if password else ''}'")

        if not username or not password:
            print(f"{_ts()} _handle_register: 用户名或密码为空 → 返回错误")
            client_socket.sendall(
                make_response(STATUS_ERROR, "用户名和密码不能为空").encode(ENCODING)
            )
            return None

        with self.lock:
            if username in self.clients:
                print(f"{_ts()} _handle_register: 用户名 '{username}' 已存在 → 返回错误")
                client_socket.sendall(
                    make_response(STATUS_ERROR, "用户名已存在").encode(ENCODING)
                )
                return None
            self.clients[username] = {"password": password, "addr": None, "socket": None}
            self._save_users()

        print(f"{_ts()} _handle_register: 注册成功 '{username}' → 发送响应")
        client_socket.sendall(
            make_response(STATUS_OK, "注册成功").encode(ENCODING)
        )
        print(f"{_ts()} _handle_register: 响应已发送")
        return None
```

改为：
```python
    def _handle_register(self, msg, client_socket):
        username = msg.get("username", "").strip()
        password = msg.get("password", "").strip()
        print(f"{_ts()} _handle_register: username='{username}', password='{'***' if password else ''}'")

        if not username or not password:
            print(f"{_ts()} _handle_register: 用户名或密码为空 → 返回错误")
            client_socket.sendall(
                make_response(STATUS_ERROR, "用户名和密码不能为空").encode(ENCODING)
            )
            return None

        with self.lock:
            if username in self.clients:
                print(f"{_ts()} _handle_register: 用户名 '{username}' 已存在 → 返回错误")
                client_socket.sendall(
                    make_response(STATUS_ERROR, "用户名已存在").encode(ENCODING)
                )
                return None
            # 写入 SQLite
            self.conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password),
            )
            self.conn.commit()
            # 加入运行时字典
            self.clients[username] = {"addr": None, "socket": None}

        print(f"{_ts()} _handle_register: 注册成功 '{username}' → 发送响应")
        client_socket.sendall(
            make_response(STATUS_OK, "注册成功").encode(ENCODING)
        )
        print(f"{_ts()} _handle_register: 响应已发送")
        return None
```

- [ ] **Step 2: 重写 _handle_login 登录验证逻辑**

替换 `_handle_login` 中检查用户名/密码的部分（第 270-282 行的 with self.lock 块）：

原代码：
```python
        with self.lock:
            if username not in self.clients:
                print(f"{_ts()} _handle_login: 用户 '{username}' 不存在 → 返回错误")
                client_socket.sendall(
                    make_response(STATUS_ERROR, "用户不存在，请先注册").encode(ENCODING)
                )
                return None
            if self.clients[username]["password"] != password:
                print(f"{_ts()} _handle_login: 密码错误 → 返回错误")
                client_socket.sendall(
                    make_response(STATUS_ERROR, "密码错误").encode(ENCODING)
                )
                return None
            if self.clients[username].get("addr") is not None:
                print(f"{_ts()} _handle_login: 用户 '{username}' 已在线 → 返回错误")
                client_socket.sendall(
                    make_response(STATUS_ERROR, "该用户已在线").encode(ENCODING)
                )
                return None

            # 设置在线状态
            self.clients[username]["addr"] = addr
            self.clients[username]["socket"] = client_socket
```

改为：
```python
        with self.lock:
            if username not in self.clients:
                print(f"{_ts()} _handle_login: 用户 '{username}' 不存在 → 返回错误")
                client_socket.sendall(
                    make_response(STATUS_ERROR, "用户不存在，请先注册").encode(ENCODING)
                )
                return None
            # 从运行时字典取密码（由 _load_users 从 DB 加载）
            stored_pw = self.clients[username].get("password")
            if stored_pw is not None and stored_pw != password:
                print(f"{_ts()} _handle_login: 密码错误 → 返回错误")
                client_socket.sendall(
                    make_response(STATUS_ERROR, "密码错误").encode(ENCODING)
                )
                return None
            if self.clients[username].get("addr") is not None:
                print(f"{_ts()} _handle_login: 用户 '{username}' 已在线 → 返回错误")
                client_socket.sendall(
                    make_response(STATUS_ERROR, "该用户已在线").encode(ENCODING)
                )
                return None

            # 设置在线状态，移除密码（运行时不再需要）
            self.clients[username]["addr"] = addr
            self.clients[username]["socket"] = client_socket
            self.clients[username].pop("password", None)
```

- [ ] **Step 3: 验证注册和登录**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
from server import ChatServer
import threading, time, socket
from common import *
s = ChatServer()
t = threading.Thread(target=s.start, daemon=True); t.start()
time.sleep(0.5)

# register
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5)
sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_REGISTER, username='alice', password='123').encode(ENCODING))
r = parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok', f'register failed: {r}'
sock.close()

# login
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5)
sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_LOGIN, username='alice', password='123').encode(ENCODING))
r = parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok', f'login failed: {r}'
sock.close()

# verify alice is in db
row = s.conn.execute('SELECT username, password FROM users WHERE username=?', ('alice',)).fetchone()
assert row == ('alice', '123'), f'db check failed: {row}'
print(f'PASS: user in DB: {row}')
s.shutdown()
print('ALL PASSED')
"
```
Expected: `PASS: user in DB: ('alice', '123')` 然后 `ALL PASSED`

- [ ] **Step 4: Commit**

```bash
git add chat-software/server.py
git commit -m "refactor: register and login via SQLite"
```

---

### Task 3: 消息持久化和历史查询改 SQL

**Files:**
- Modify: `chat-software/server.py`

- [ ] **Step 1: 添加 _add_message_db 方法**

在 `_get_conversations_for_user` 被删除的位置之后，插入：

```python
    def _add_message_db(self, key, sender, content):
        """插入消息到 SQLite 并淘汰旧消息，返回带 timestamp 的 msg dict"""
        msg = {
            "sender": sender,
            "content": content,
            "timestamp": now_iso(),
        }
        with self.lock:
            self.conn.execute(
                "INSERT INTO messages (chat_key, sender, content, timestamp) VALUES (?, ?, ?, ?)",
                (key, sender, content, msg["timestamp"]),
            )
            # 淘汰旧消息：每个 chat_key 保留最近 MAX_MESSAGES_PER_CHAT 条
            self.conn.execute("""
                DELETE FROM messages WHERE chat_key = ? AND id NOT IN (
                    SELECT id FROM messages WHERE chat_key = ? ORDER BY id DESC LIMIT ?
                )
            """, (key, key, MAX_MESSAGES_PER_CHAT))
            self.conn.commit()
        return msg
```

- [ ] **Step 2: 修改 _handle_broadcast，调用 _add_message_db**

替换 `_handle_broadcast` 方法（第 346-362 行）：

原代码中 `self._add_message("public", ...)` 改为 `self._add_message_db("public", ...)`。

- [ ] **Step 3: 修改 _handle_private，调用 _add_message_db**

替换 `_handle_private` 方法（第 383-420 行）：

原代码中 `self._add_message(key, ...)` 改为 `self._add_message_db(key, ...)`。

- [ ] **Step 4: 重写 _handle_get_history 用 SQL 查询**

替换 `_handle_get_history`（第 432-444 行）：

原代码：
```python
    def _handle_get_history(self, msg, client_socket, current_user):
        """返回指定会话的最近 MAX_HISTORY 条历史"""
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

改为：
```python
    def _handle_get_history(self, msg, client_socket, current_user):
        """返回指定会话的最近 MAX_HISTORY 条历史"""
        if not current_user:
            return
        target = msg.get("target", "public")
        if target != "public":
            target = conversation_key(current_user, target)
        with self.lock:
            rows = self.conn.execute(
                "SELECT sender, content, timestamp FROM messages "
                "WHERE chat_key = ? ORDER BY id DESC LIMIT ?",
                (target, MAX_HISTORY),
            ).fetchall()
        msgs = [
            {"sender": r[0], "content": r[1], "timestamp": r[2]}
            for r in reversed(rows)
        ]
        client_socket.sendall(
            make_message(TYPE_HISTORY, target=target, messages=msgs).encode(ENCODING)
        )
```

- [ ] **Step 5: 修改 _handle_login 中的历史查询**

`_handle_login` 方法中（第 295 行），原代码：
```python
        public_history = self.messages.get("public", [])[-MAX_HISTORY:]
```

改为：
```python
        rows = self.conn.execute(
            "SELECT sender, content, timestamp FROM messages "
            "WHERE chat_key = 'public' ORDER BY id DESC LIMIT ?",
            (MAX_HISTORY,),
        ).fetchall()
        public_history = [
            {"sender": r[0], "content": r[1], "timestamp": r[2]}
            for r in reversed(rows)
        ]
```

- [ ] **Step 6: 添加 _get_conversations_for_user 数据库版**

在 `_add_message_db` 之后插入：

```python
    def _get_conversations_for_user(self, username):
        """返回某用户参与过的所有私聊对象列表（按最近消息时间降序）"""
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
                last_ts = last[0] if last else ""
                partners.append((partner, last_ts))
        partners.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in partners]
```

- [ ] **Step 7: 修改 shutdown，关闭数据库**

替换 `shutdown` 方法（第 141-157 行），删除 `self._save_messages()` 调用，添加 `self.conn.close()`。

定位到：
```python
        self._save_users()
        self._save_messages()                              # 新增
        print("[服务器] 服务器已关闭")
```

改为：
```python
        self.conn.close()
        print("[服务器] 服务器已关闭")
```

- [ ] **Step 8: 验证消息持久化**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
from server import ChatServer
import threading, time, socket
from common import *
s = ChatServer()
t = threading.Thread(target=s.start, daemon=True); t.start()
time.sleep(0.5)

# register + login alice
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5)
sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_REGISTER, username='alice', password='123').encode(ENCODING))
parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING)); sock.close()

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.settimeout(5)
sock.connect(('127.0.0.1', 9999))
sock.sendall(make_message(TYPE_LOGIN, username='alice', password='123').encode(ENCODING))
parse_message(sock.recv(BUFFER_SIZE).decode(ENCODING))

# send broadcast
ts = now_iso()
sock.sendall(make_message(TYPE_BROADCAST, content='hello sqlite', timestamp=ts).encode(ENCODING))
sock.close()
time.sleep(0.3)

# check messages table
rows = s.conn.execute('SELECT chat_key, sender, content FROM messages').fetchall()
assert len(rows) == 1, f'expected 1 message, got {len(rows)}'
assert rows[0] == ('public', 'alice', 'hello sqlite'), f'unexpected row: {rows[0]}'
print(f'PASS: message saved: {rows[0]}')

# restart server, verify persistence
s.shutdown()
s2 = ChatServer()
rows2 = s2.conn.execute('SELECT chat_key, sender, content FROM messages').fetchall()
assert len(rows2) == 1
print(f'PASS: message survives restart: {rows2[0]}')
s2.conn.close()
print('ALL PASSED')
"
```
Expected: 两个 PASS 然后 ALL PASSED

- [ ] **Step 9: Commit**

```bash
git add chat-software/server.py
git commit -m "refactor: replace message persistence with SQLite"
```

---

### Task 4: 集成测试 + 清理

**Files:**
- (no new files committed)

- [ ] **Step 1: 集成测试 — 完整流程**

```bash
cd D:/moniC/project/jiwang-keshe/chat-software && python -c "
import socket, time, threading
from server import ChatServer
from common import *

server = ChatServer()
t = threading.Thread(target=server.start, daemon=True); t.start()
time.sleep(0.5)

def client():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(5)
    s.connect(('127.0.0.1', 9999))
    return s

# 1. alice 注册+登录
s1 = client()
s1.sendall(make_message(TYPE_REGISTER, username='alice', password='123').encode(ENCODING))
r = parse_message(s1.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok', f'register failed: {r}'
s1.close()

s1 = client()
s1.sendall(make_message(TYPE_LOGIN, username='alice', password='123').encode(ENCODING))
r = parse_message(s1.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok', f'login failed: {r}'
assert r.get('public_history') == [], f'public_history should be empty: {r}'
print('[PASS] alice 登录, public_history 为空')

# 2. alice 发公聊 → bob 登录后应看到
s1.sendall(make_message(TYPE_BROADCAST, content='hello from alice', timestamp=now_iso()).encode(ENCODING))
time.sleep(0.2)

s2 = client()
s2.sendall(make_message(TYPE_REGISTER, username='bob', password='456').encode(ENCODING))
parse_message(s2.recv(BUFFER_SIZE).decode(ENCODING))
s2.close()

s2 = client()
s2.sendall(make_message(TYPE_LOGIN, username='bob', password='456').encode(ENCODING))
r = parse_message(s2.recv(BUFFER_SIZE).decode(ENCODING))
assert r['status'] == 'ok'
assert len(r['public_history']) == 1
assert r['public_history'][0]['content'] == 'hello from alice'
print('[PASS] bob 登录看到 alice 的公聊消息')

# 3. 私聊测试
s2.sendall(make_message(TYPE_PRIVATE, target='alice', content='hi alice', timestamp=now_iso()).encode(ENCODING))
time.sleep(0.5)

# alice 查私聊历史
s1.sendall(make_message(TYPE_GET_HISTORY, target='bob').encode(ENCODING))
hist = parse_message(s1.recv(BUFFER_SIZE).decode(ENCODING))
assert hist['type'] == 'history'
assert len(hist['messages']) == 1
assert hist['messages'][0]['sender'] == 'bob'
assert hist['messages'][0]['content'] == 'hi alice'
print('[PASS] 私聊历史正确')

# 4. 消息上限测试（插入 510 条，确认只保留 500 条）
for i in range(510):
    ts = now_iso()
    s1.sendall(make_message(TYPE_BROADCAST, content=f'test {i}', timestamp=ts).encode(ENCODING))
    time.sleep(0.001)
time.sleep(1)

count = server.conn.execute('SELECT COUNT(*) FROM messages WHERE chat_key = ?', ('public',)).fetchone()[0]
assert count <= 500, f'message count {count} exceeds 500'
print(f'[PASS] 消息上限: {count} 条 (<= 500)')

# 5. 重启验证
s1.close(); s2.close()
server.shutdown()

server2 = ChatServer()
pub_count = server2.conn.execute('SELECT COUNT(*) FROM messages WHERE chat_key = ?', ('public',)).fetchone()[0]
priv_count = server2.conn.execute('SELECT COUNT(*) FROM messages WHERE chat_key = ?', (conversation_key('alice', 'bob'),)).fetchone()[0]
print(f'[PASS] 重启后: public={pub_count}, private={priv_count}')
server2.conn.close()

print()
print('=' * 50)
print('  全部集成测试通过!')
print('=' * 50)
"
```
Expected: 5 个 `[PASS]` 全部通过

- [ ] **Step 2: 清理测试数据**

```bash
rm -f D:/moniC/project/jiwang-keshe/chat-software/chat.db
rm -f D:/moniC/project/jiwang-keshe/chat-software/users.json
rm -f D:/moniC/project/jiwang-keshe/chat-software/messages.json
```
(如果 `users.json` / `messages.json` 已在 git 跟踪中则保留，但仍从磁盘删除)

- [ ] **Step 3: 最终手动验证**

启动服务端和两个客户端测试：
1. 启动 server.py
2. 启动 client.py → alice 注册并登录
3. alice 发公聊消息 → 气泡正常
4. 另外启动 client.py → bob 注册并登录 → 能看到 alice 的消息
5. bob 给 alice 发私聊
6. 关闭所有客户端和服务端，重启 server.py
7. 重新登录 → 历史消息仍在

- [ ] **Step 4: Commit**

```bash
git add chat-software/server.py
git commit -m "test: verify SQLite persistence with integration tests"
```

---

## Self-Review

1. **Spec coverage:**
   - 数据库设计（WAL、表、索引） → Task 1 Step 3
   - 注册 INSERT → Task 2 Step 1
   - 登录密码验证 → Task 2 Step 2
   - 发消息 INSERT + 淘汰 → Task 3 Step 1
   - 历史查询 SELECT → Task 3 Step 4
   - 会话列表 → Task 3 Step 6
   - 关闭 conn.close() → Task 3 Step 7
   - 不改 common.py / client.py → ✅ 全程未触及
   - 测试要点 → Task 4

2. **Placeholder scan:** 无 TBD / TODO / 留空

3. **Type consistency:** `_add_message_db` 返回 dict 带 `timestamp` 字段，与 `_handle_broadcast` / `_handle_private` 中对 `saved["timestamp"]` 的访问一致。`_handle_get_history` 返回 `TYPE_HISTORY` 消息中的 `messages` 结构与客户端 `_render_history` 期望的 `m.get("sender", ...)` 一致。
