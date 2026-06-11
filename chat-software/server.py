"""
聊天服务端：多线程处理并发客户端连接
功能：用户注册/登录、公聊广播、私聊转发、在线用户列表
"""

import socket
import threading
import json
import os
import time

from common import (
    DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE, ENCODING,
    TYPE_REGISTER, TYPE_LOGIN, TYPE_BROADCAST, TYPE_PRIVATE,
    TYPE_GET_USERS, TYPE_RESPONSE, TYPE_SYSTEM,
    TYPE_GET_HISTORY, TYPE_HISTORY,
    MAX_HISTORY, MAX_MESSAGES_PER_CHAT,
    STATUS_OK, STATUS_ERROR,
    make_message, parse_message, make_response, make_system_msg,
    now_iso, conversation_key,
)

USERS_FILE = "users.json"
MESSAGES_FILE = "messages.json"


def _ts():
    """返回带时间戳的前缀，用于日志"""
    return time.strftime("[%H:%M:%S]")


class ChatServer:
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

    # ========================
    #  用户数据持久化
    # ========================
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

    def _save_users(self):
        """持久化已注册用户（仅保存密码）。调用方可以持有锁，本方法会自行加锁。"""
        with self.lock:
            data = {u: info["password"] for u, info in self.clients.items()}
        with open(USERS_FILE, "w", encoding=ENCODING) as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ========================
    #  消息持久化
    # ========================
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
        """持久化消息到磁盘"""
        with self.lock:
            data = self.messages
        with open(MESSAGES_FILE, "w", encoding=ENCODING) as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _add_message(self, key, sender, content):
        """添加一条消息到 messages 并持久化，返回带 timestamp 的 msg dict"""
        msg = {
            "sender": sender,
            "content": content,
            "timestamp": now_iso(),
        }
        with self.lock:
            if key not in self.messages:
                self.messages[key] = []
            self.messages[key].append(msg)
            if len(self.messages[key]) > MAX_MESSAGES_PER_CHAT:
                self.messages[key] = self.messages[key][-MAX_MESSAGES_PER_CHAT:]
        self._save_messages()
        return msg

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
        self._save_users()
        self._save_messages()                              # 新增
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
        elif msg_type == TYPE_GET_HISTORY:                    # 新增
            self._handle_get_history(msg, client_socket, current_user)
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
            self.clients[username] = {"password": password, "addr": None, "socket": None}
            self._save_users()

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

        print(f"{_ts()} _handle_login: 登录成功 '{username}' → 发送响应")
        public_history = self.messages.get("public", [])[-MAX_HISTORY:]
        conversations = self._get_conversations_for_user(username)
        login_resp = make_message(
            TYPE_RESPONSE, status=STATUS_OK, message="登录成功",
            public_history=public_history, conversations=conversations,
        )
        client_socket.sendall(login_resp.encode(ENCODING))
        print(f"{_ts()} _handle_login: 响应已发送, 广播上线通知")

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
        saved = self._add_message("public", current_user, content)
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
        # 如果是私聊会话，用 conversation_key 构造真正的 key
        if target != "public":
            target = conversation_key(current_user, target)
        with self.lock:
            msgs = self.messages.get(target, [])[-MAX_HISTORY:]
        client_socket.sendall(
            make_message(TYPE_HISTORY, target=target, messages=msgs).encode(ENCODING)
        )


if __name__ == "__main__":
    server = ChatServer()
    server.start()
