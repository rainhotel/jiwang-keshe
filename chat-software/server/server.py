"""
服务端核心：TCP 连接管理、消息分派、文件传输
"""

import socket
import threading
import json
import os
import time

from common.protocol import (
    DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE, ENCODING,
    TYPE_FILE_NOTIFY,
    FILE_PORT, FILE_CHUNK,
    STATUS_ERROR,
    make_message, make_system_msg, make_response,
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
        self.clients = {}  # {username: {"password": str, "addr": tuple|None, "socket": socket|None}}
        self.lock = threading.RLock()
        self.send_lock = threading.Lock()
        # socket → username 映射
        self._sock_user = {}

        users = db.load_users()
        for username, password in users.items():
            self.clients[username] = {"password": password, "addr": None, "socket": None}
        print(f"[服务器] 已加载 {len(users)} 个已注册用户")

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
        msg = make_system_msg(content) if system else content
        data = msg.encode(ENCODING) if isinstance(msg, str) else msg
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

    # ========================
    #  文件通知
    # ========================
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

    # ========================
    #  文件传输
    # ========================
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
                    receiver, filename, fsize, sender, chat_key = row
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
                        self._notify_file_to_user(notify_data, receiver)
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

    # ========================
    #  客户端连接处理
    # ========================
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
                        if msg_type == "login":
                            obj["_addr"] = addr
                        result = handler(obj, client_socket, self, self.db)
                        if msg_type == "login" and result:
                            username = result
                            self._set_current_user(client_socket, username)
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
            if username and username in self._sock_user:
                del self._sock_user[client_socket]
            try:
                client_socket.close()
            except Exception:
                pass

    # ========================
    #  启动 / 关闭
    # ========================
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
