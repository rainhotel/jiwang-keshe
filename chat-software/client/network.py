"""
客户端网络层：TCP 连接、消息收发、JSON 解析、回调分发
"""

import socket
import json
import threading

from common.protocol import (
    BUFFER_SIZE, ENCODING,
    make_message, parse_message,
)


class NetworkClient:
    def __init__(self):
        self.sock = None
        self.running = False
        self.handlers = {}  # {msg_type: callback(msg_dict)}
        self.recv_thread = None

    def connect(self, host, port, timeout=5):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect((host, port))
            return None  # no error
        except Exception as e:
            return f"无法连接到服务器: {e}"

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    # ========================
    #  发送
    # ========================
    def send(self, msg_type, **kwargs):
        data = make_message(msg_type, **kwargs).encode(ENCODING)
        self.sock.sendall(data)

    def send_raw(self, data):
        self.sock.sendall(data)

    def send_and_wait(self, msg_type, timeout=5, **kwargs):
        """发送并等待响应（登录/注册用）"""
        self.sock.settimeout(timeout)
        data = make_message(msg_type, **kwargs).encode(ENCODING)
        self.sock.sendall(data)
        resp_data = self.sock.recv(BUFFER_SIZE)
        resp = parse_message(resp_data.decode(ENCODING))
        return resp

    # ========================
    #  接收
    # ========================
    def set_handler(self, msg_type, callback):
        self.handlers[msg_type] = callback

    def start_receive(self):
        """启动后台接收线程"""
        self.sock.settimeout(None)
        self.running = True
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()

    def _dispatch(self, msg_type, msg):
        cb = self.handlers.get(msg_type)
        if cb:
            cb(msg)

    def _recv_loop(self):
        buffer = ""
        decoder = json.JSONDecoder()
        while self.running:
            try:
                data = self.sock.recv(BUFFER_SIZE)
                if not data:
                    self._dispatch("system_disconnect", {})
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
                        self._dispatch(obj.get("type"), obj)
                    except json.JSONDecodeError:
                        break
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                self._dispatch("system_disconnect", {})
                break
            except Exception as e:
                self._dispatch("system_error", {"error": str(e)})
                break
