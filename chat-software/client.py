"""
聊天客户端：tkinter GUI
功能：连接服务器、注册/登录、公聊、私聊、在线用户列表
"""

import json
import socket
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog

from common import (
    DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE, ENCODING,
    TYPE_REGISTER, TYPE_LOGIN, TYPE_BROADCAST, TYPE_PRIVATE,
    TYPE_GET_USERS, TYPE_SYSTEM, TYPE_RESPONSE,
    STATUS_OK, STATUS_ERROR,
    make_message, parse_message,
)


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
    def __init__(self, socket_conn, username):
        self.socket = socket_conn
        self.username = username
        self.running = True

        self.root = tk.Tk()
        self.root.title(f"局域网聊天 - {username}")
        self.root.geometry("700x500")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 左侧聊天区域
        frm_chat = tk.Frame(self.root)
        frm_chat.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)

        self.chat_display = scrolledtext.ScrolledText(
            frm_chat, state="disabled", wrap="word", font=("微软雅黑", 10)
        )
        self.chat_display.pack(fill="both", expand=True)

        # 输入区域
        frm_input = tk.Frame(frm_chat)
        frm_input.pack(fill="x", pady=(3, 0))
        self.entry_msg = tk.Entry(frm_input, font=("微软雅黑", 10))
        self.entry_msg.pack(side="left", fill="x", expand=True)
        self.entry_msg.bind("<Return>", self.send_message)
        tk.Button(frm_input, text="发送", width=8, command=self.send_message).pack(side="right", padx=(3, 0))

        # 右侧面板
        frm_right = tk.Frame(self.root, width=160)
        frm_right.pack(side="right", fill="y", padx=(5, 5), pady=5)
        frm_right.pack_propagate(False)

        # 在线用户
        lbl_online = tk.Label(frm_right, text="在线用户", font=("微软雅黑", 10, "bold"))
        lbl_online.pack()
        self.user_listbox = tk.Listbox(frm_right, font=("微软雅黑", 9))
        self.user_listbox.pack(fill="both", expand=True, pady=3)
        self.user_listbox.bind("<Double-Button-1>", self.start_private_chat)

        # 帮助
        lbl_help = tk.Label(
            frm_right,
            text="双击用户发起私聊\n直接发送为公聊\n@用户名 消息 为私聊",
            font=("微软雅黑", 8),
            fg="gray",
            justify="left",
        )
        lbl_help.pack(pady=5)

        # 启动接收线程
        self.recv_thread = threading.Thread(target=self.receive_loop, daemon=True)
        self.recv_thread.start()

        # 居中
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

        self.append_text("[系统] 欢迎来到聊天室！\n", "blue")
        self.refresh_users()

    # ========================
    #  界面更新（线程安全）
    # ========================
    def append_text(self, text, tag=None):
        """在主线程中追加聊天文本"""
        def _append():
            self.chat_display.config(state="normal")
            self.chat_display.insert("end", text, tag)
            self.chat_display.see("end")
            self.chat_display.config(state="disabled")
        self.root.after(0, _append)

    def refresh_users(self):
        """请求并刷新在线用户列表"""
        try:
            self.socket.sendall(
                make_message(TYPE_GET_USERS).encode(ENCODING)
            )
        except Exception:
            pass

    def update_user_list(self, users):
        """更新右侧在线用户列表"""
        def _update():
            self.user_listbox.delete(0, "end")
            for u in users:
                display = f"● {u}"
                self.user_listbox.insert("end", display)
        self.root.after(0, _update)

    # ========================
    #  消息接收循环
    # ========================
    def receive_loop(self):
        """后台线程：持续接收服务器消息，处理 TCP 粘包"""
        buffer = ""
        decoder = json.JSONDecoder()
        while self.running:
            try:
                data = self.socket.recv(BUFFER_SIZE)
                if not data:
                    self.append_text("[系统] 与服务器断开连接\n", "red")
                    break
                buffer += data.decode(ENCODING)

                # 循环解析 buffer 中的所有完整 JSON 对象
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
                        break  # 数据不完整，等下次 recv
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                if self.running:
                    self.append_text("[系统] 与服务器断开连接\n", "red")
                break
            except Exception as e:
                if self.running:
                    self.append_text(f"[系统] 接收异常: {e}\n", "red")
                break

    def _handle_message(self, msg):
        msg_type = msg.get("type")
        if msg_type == TYPE_BROADCAST:
            sender = msg.get("sender", "未知")
            content = msg.get("content", "")
            if sender == "[系统]":
                self.append_text(f"{content}\n", "blue")
            else:
                self.append_text(f"[{sender}] {content}\n")
        elif msg_type == TYPE_PRIVATE:
            sender = msg.get("sender", "未知")
            content = msg.get("content", "")
            self.append_text(f"[私聊] {sender} -> 你: {content}\n", "green")
        elif msg_type == TYPE_GET_USERS:
            self.update_user_list(msg.get("users", []))

    # ========================
    #  发送消息
    # ========================
    def send_message(self, event=None):
        content = self.entry_msg.get().strip()
        if not content:
            return
        self.entry_msg.delete(0, "end")

        # 判断是否为私聊格式: @用户名 消息
        if content.startswith("@"):
            parts = content.split(" ", 1)
            if len(parts) >= 2:
                target = parts[0][1:]  # 去掉@
                msg_content = parts[1]
                msg = make_message(TYPE_PRIVATE, target=target, content=msg_content)
                try:
                    self.socket.sendall(msg.encode(ENCODING))
                except Exception as e:
                    self.append_text(f"[系统] 发送失败: {e}\n", "red")
                return
            else:
                self.append_text("[系统] 私聊格式: @用户名 消息内容\n", "red")
                return

        # 公聊
        msg = make_message(TYPE_BROADCAST, content=content)
        try:
            self.socket.sendall(msg.encode(ENCODING))
        except Exception as e:
            self.append_text(f"[系统] 发送失败: {e}\n", "red")
            return
        # 本地回声：服务端广播排除了发送者，需要自己显示
        self.append_text(f"[{self.username}] {content}\n")

    def start_private_chat(self, event=None):
        """双击在线用户发起私聊"""
        selection = self.user_listbox.curselection()
        if not selection:
            return
        display = self.user_listbox.get(selection[0])  # "● username"
        target = display[2:]  # 去掉 "● "
        if target == self.username:
            return
        text = simpledialog.askstring("私聊", f"发送给 {target}:")
        if text and text.strip():
            self.entry_msg.delete(0, "end")
            self.entry_msg.insert(0, f"@{target} {text.strip()}")
            self.send_message()

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
        chat = ChatWindow(login.socket, login.username)
        chat.run()
