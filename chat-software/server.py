"""
聊天服务端：多线程处理并发客户端连接
功能：用户注册/登录、公聊广播、私聊转发、在线用户列表
"""

import socket
import threading
import json
import os
import sqlite3
import time

from common import (
    DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE, ENCODING,
    TYPE_REGISTER, TYPE_LOGIN, TYPE_BROADCAST, TYPE_PRIVATE,
    TYPE_GET_USERS, TYPE_RESPONSE, TYPE_SYSTEM,
    TYPE_GET_HISTORY, TYPE_HISTORY,
    TYPE_CREATE_GROUP, TYPE_JOIN_GROUP, TYPE_LEAVE_GROUP,
    TYPE_DELETE_GROUP, TYPE_GROUP_USERS, TYPE_GROUP_MSG,
    MAX_HISTORY, MAX_MESSAGES_PER_CHAT,
    STATUS_OK, STATUS_ERROR,
    make_message, parse_message, make_response, make_system_msg,
    now_iso, conversation_key, group_key,
)

DB_FILE = "chat.db"


def _ts():
    """返回带时间戳的前缀，用于日志"""
    return time.strftime("[%H:%M:%S]")


class ChatServer:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        # {username: {"addr": tuple, "socket": socket}}
        self.clients = {}            # 仅存运行时状态，不再存密码
        self.lock = threading.RLock()
        self._init_db()
        self._load_users()

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
        self.conn.commit()

    # ========================
    #  用户数据持久化
    # ========================
    def _load_users(self):
        """从 SQLite 加载已注册用户到运行时字典"""
        rows = self.conn.execute(
            "SELECT username, password FROM users"
        ).fetchall()
        for username, password in rows:
            self.clients[username] = {"password": password, "addr": None, "socket": None}
        print(f"[服务器] 已加载 {len(rows)} 个已注册用户")

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
            self.conn.execute("""
                DELETE FROM messages WHERE chat_key = ? AND id NOT IN (
                    SELECT id FROM messages WHERE chat_key = ? ORDER BY id DESC LIMIT ?
                )
            """, (key, key, MAX_MESSAGES_PER_CHAT))
            self.conn.commit()
        return msg

    # ========================
    #  服务器启动
    # ========================
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(50)
        print(f"[服务器] 聊天服务器启动成功：{self.host}:{self.port}")
        print("[服务器] 等待客户端连接...")

        try:
            while True:
                client_socket, addr = self.server_socket.accept()
                print(f"[服务器] 新连接来自 {addr}")
                thread = threading.Thread(
                    target=self.handle_client, args=(client_socket, addr), daemon=True
                )
                thread.start()
        except KeyboardInterrupt:
            print("\n[服务器] 服务器正在关闭...")
        finally:
            self.shutdown()

    def shutdown(self):
        """安全关闭服务器"""
        # 通知所有在线用户
        with self.lock:
            for u, info in self.clients.items():
                if info.get("addr"):
                    try:
                        sock = info.get("socket")
                        if sock:
                            sock.sendall(make_system_msg("服务器已关闭，再见！").encode(ENCODING))
                    except Exception:
                        pass
        if self.server_socket:
            self.server_socket.close()
        self.conn.close()
        print("[服务器] 服务器已关闭")

    # ========================
    #  客户端处理
    # ========================
    def handle_client(self, client_socket, addr):
        """处理单个客户端连接，处理 TCP 粘包"""
        username = None
        buffer = ""
        decoder = json.JSONDecoder()
        print(f"{_ts()} [线程-{threading.current_thread().name}] handle_client 开始: {addr}")

        try:
            while True:
                print(f"{_ts()} [线程-{threading.current_thread().name}] 等待 recv...")
                data = client_socket.recv(BUFFER_SIZE)
                if not data:
                    print(f"{_ts()} [线程-{threading.current_thread().name}] recv 返回空, 客户端关闭连接")
                    break

                buffer += data.decode(ENCODING)
                print(f"{_ts()} [线程-{threading.current_thread().name}] recv 收到 {len(data)} 字节, buffer={len(buffer)}字节")

                # 循环解析 buffer 中的所有完整 JSON 对象
                while buffer:
                    stripped = buffer.lstrip()
                    if not stripped:
                        buffer = ""
                        break
                    try:
                        obj, end = decoder.raw_decode(stripped)
                        buffer = stripped[end:]
                    except json.JSONDecodeError:
                        break  # 数据不完整，等下次 recv

                    msg_type = obj.get("type")
                    print(f"{_ts()} [线程-{threading.current_thread().name}] 消息类型={msg_type}, 内容={obj}")
                    username = self._dispatch(msg_type, obj, client_socket, addr, username)

        except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
            print(f"{_ts()} [线程-{threading.current_thread().name}] 连接异常: {e}")
        finally:
            print(f"{_ts()} [线程-{threading.current_thread().name}] handle_client 结束: user={username}")
            self._disconnect_client(username, client_socket)

    def _dispatch(self, msg_type, msg, client_socket, addr, current_user):
        """消息分派"""
        if msg_type == TYPE_REGISTER:
            return self._handle_register(msg, client_socket)
        elif msg_type == TYPE_LOGIN:
            new_user = self._handle_login(msg, client_socket, addr)
            return new_user if new_user else current_user
        elif msg_type == TYPE_BROADCAST:
            self._handle_broadcast(msg, client_socket, current_user)
        elif msg_type == TYPE_PRIVATE:
            self._handle_private(msg, client_socket, current_user)
        elif msg_type == TYPE_GET_USERS:
            self._handle_get_users(client_socket)
        elif msg_type == TYPE_GET_HISTORY:
            self._handle_get_history(msg, client_socket, current_user)
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
        else:
            client_socket.sendall(
                make_response(STATUS_ERROR, f"未知消息类型: {msg_type}").encode(ENCODING)
            )
        return current_user

    # ========================
    #  注册处理
    # ========================
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
            self.clients[username] = {"password": password, "addr": None, "socket": None}

        print(f"{_ts()} _handle_register: 注册成功 '{username}' → 发送响应")
        client_socket.sendall(
            make_response(STATUS_OK, "注册成功").encode(ENCODING)
        )
        print(f"{_ts()} _handle_register: 响应已发送")
        return None

    # ========================
    #  登录处理
    # ========================
    def _handle_login(self, msg, client_socket, addr):
        username = msg.get("username", "").strip()
        password = msg.get("password", "").strip()
        print(f"{_ts()} _handle_login: username='{username}', password='{'***' if password else ''}'")

        if not username or not password:
            print(f"{_ts()} _handle_login: 用户名或密码为空 → 返回错误")
            client_socket.sendall(
                make_response(STATUS_ERROR, "用户名和密码不能为空").encode(ENCODING)
            )
            return None

        with self.lock:
            if username not in self.clients:
                print(f"{_ts()} _handle_login: 用户 '{username}' 不存在 → 返回错误")
                client_socket.sendall(
                    make_response(STATUS_ERROR, "用户不存在，请先注册").encode(ENCODING)
                )
                return None
            # 密码验证（首次登录用缓存，重连时密码仍保留在 dict 中）
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

            # 设置在线状态
            self.clients[username]["addr"] = addr
            self.clients[username]["socket"] = client_socket

        # 查询公聊历史
        rows = self.conn.execute(
            "SELECT sender, content, timestamp FROM messages "
            "WHERE chat_key = 'public' ORDER BY id DESC LIMIT ?",
            (MAX_HISTORY,),
        ).fetchall()
        public_history = [
            {"sender": r[0], "content": r[1], "timestamp": r[2]}
            for r in reversed(rows)
        ]
        conversations = self._get_conversations_for_user(username)
        login_resp = make_message(
            TYPE_RESPONSE, status=STATUS_OK, message="登录成功",
            public_history=public_history, conversations=conversations,
        )
        client_socket.sendall(login_resp.encode(ENCODING))

        # 广播上线通知
        self.broadcast(f"{username} 加入了聊天室", system=True, exclude=username)
        return username

    # ========================
    #  断开连接
    # ========================
    def _disconnect_client(self, username, client_socket):
        if username:
            print(f"[服务器] 用户断开: {username}")
            with self.lock:
                if username in self.clients:
                    self.clients[username]["addr"] = None
                    self.clients[username]["socket"] = None
            self.broadcast(f"{username} 离开了聊天室", system=True, exclude=username)
        try:
            client_socket.close()
        except Exception:
            pass

    # ========================
    #  消息广播
    # ========================
    def broadcast(self, content, system=False, exclude=None):
        """向所有在线用户广播消息"""
        if system:
            msg = make_system_msg(content)
        else:
            msg = content  # 已经是JSON字符串

        data = msg.encode(ENCODING)
        with self.lock:
            for u, info in list(self.clients.items()):
                if u == exclude:
                    continue
                sock = info.get("socket")
                if sock:
                    try:
                        sock.sendall(data)
                    except Exception:
                        pass

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
        saved = self._add_message_db("public", current_user, content)
        full_msg = make_message(
            TYPE_BROADCAST, content=content, sender=current_user,
            timestamp=saved["timestamp"],
        )
        print(f"[公聊] {current_user}: {content}")
        self.broadcast(full_msg, exclude=current_user)

    # ========================
    #  私聊消息
    # ========================
    def private_message(self, target, content, sender):
        """发送私聊消息"""
        msg = make_message(
            TYPE_PRIVATE, content=content, sender=sender, target=target
        )
        data = msg.encode(ENCODING)
        with self.lock:
            target_info = self.clients.get(target)
            if target_info and target_info.get("socket"):
                try:
                    target_info["socket"].sendall(data)
                    return True
                except Exception:
                    return False
        return False

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
        saved = self._add_message_db(key, current_user, content)

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

    # ========================
    #  在线用户列表
    # ========================
    def _handle_get_users(self, client_socket):
        with self.lock:
            online = [u for u, info in self.clients.items() if info.get("addr") is not None]
        client_socket.sendall(
            make_message(TYPE_GET_USERS, users=online).encode(ENCODING)
        )

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
            row = self.conn.execute("SELECT id, name FROM groups WHERE id=?", (gid,)).fetchone()
            if not row:
                client_socket.sendall(
                    make_response(STATUS_ERROR, "群不存在").encode(ENCODING)
                )
                return
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


if __name__ == "__main__":
    server = ChatServer()
    server.start()
