"""
登录/注册窗口
"""

import threading
import tkinter as tk
from tkinter import messagebox

from common.protocol import (
    DEFAULT_HOST, DEFAULT_PORT,
    TYPE_LOGIN, TYPE_REGISTER,
    STATUS_OK,
)
from client.network import NetworkClient


class LoginWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("局域网聊天 - 登录")
        self.root.geometry("360x280")
        self.root.resizable(False, False)

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

        frm_auth = tk.LabelFrame(self.root, text="用户信息", padx=5, pady=5)
        frm_auth.pack(fill="x", padx=10, pady=5)

        tk.Label(frm_auth, text="用户名:").grid(row=0, column=0, sticky="e", pady=3)
        self.entry_user = tk.Entry(frm_auth, width=25)
        self.entry_user.grid(row=0, column=1, padx=5, pady=3)

        tk.Label(frm_auth, text="密  码:").grid(row=1, column=0, sticky="e", pady=3)
        self.entry_pass = tk.Entry(frm_auth, width=25, show="*")
        self.entry_pass.grid(row=1, column=1, padx=5, pady=3)

        frm_btn = tk.Frame(self.root)
        frm_btn.pack(pady=10)
        tk.Button(frm_btn, text="登录", width=10, command=self.do_login).pack(side="left", padx=5)
        tk.Button(frm_btn, text="注册", width=10, command=self.do_register).pack(side="left", padx=5)

        self.nc = None  # NetworkClient
        self.username = None
        self._login_public_history = []
        self._login_conversations = []
        self._login_groups = []
        self._login_contacts = []

        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _get_params(self):
        """在主线程读取控件值"""
        return (
            self.entry_host.get().strip(),
            self.entry_port.get().strip(),
            self.entry_user.get().strip(),
            self.entry_pass.get().strip(),
        )

    def _validate_port(self, port_str):
        try:
            return int(port_str), None
        except ValueError:
            return None, "端口号必须为数字"

    def do_login(self):
        host, port_str, username, password = self._get_params()
        if not username or not password:
            messagebox.showwarning("提示", "请输入用户名和密码")
            return
        port, err = self._validate_port(port_str)
        if err:
            messagebox.showerror("错误", err)
            return

        def _run():
            nc = NetworkClient()
            err = nc.connect(host, port)
            if err:
                self.root.after(0, lambda e=err: messagebox.showerror("连接失败", e))
                return
            resp = nc.send_and_wait(TYPE_LOGIN, username=username, password=password)
            if resp and resp.get("status") == STATUS_OK:
                self.nc = nc
                self.username = username
                self._login_public_history = resp.get("public_history", [])
                self._login_conversations = resp.get("conversations", [])
                self._login_groups = resp.get("groups", [])
                self._login_contacts = resp.get("contacts", [])
                self.root.after(0, self.root.destroy)
            else:
                msg = resp.get("message", "登录失败") if resp else "服务器无响应"
                self.root.after(0, lambda m=msg: messagebox.showerror("登录失败", m))
                nc.close()

        threading.Thread(target=_run, daemon=True).start()

    def do_register(self):
        host, port_str, username, password = self._get_params()
        if not username or not password:
            messagebox.showwarning("提示", "请输入用户名和密码")
            return
        port, err = self._validate_port(port_str)
        if err:
            messagebox.showerror("错误", err)
            return

        def _run():
            nc = NetworkClient()
            err = nc.connect(host, port)
            if err:
                self.root.after(0, lambda e=err: messagebox.showerror("连接失败", e))
                return
            resp = nc.send_and_wait(TYPE_REGISTER, username=username, password=password)
            if resp and resp.get("status") == STATUS_OK:
                self.root.after(0, lambda: messagebox.showinfo("成功", "注册成功！请登录"))
            else:
                msg = resp.get("message", "注册失败") if resp else "服务器无响应"
                self.root.after(0, lambda m=msg: messagebox.showerror("注册失败", m))
            nc.close()

        threading.Thread(target=_run, daemon=True).start()

    def run(self):
        self.root.mainloop()
        return self
