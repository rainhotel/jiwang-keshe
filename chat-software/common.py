"""
公共模块：协议常量、消息序列化/反序列化
"""

import json

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
TYPE_GET_HISTORY = "get_history"   # 客户端→服务端, {"target": "public" | "alice"}
TYPE_HISTORY     = "history"       # 服务端→客户端, {"target": "...", "messages": [...]}

MAX_HISTORY = 50                   # 每次拉取历史条数
MAX_MESSAGES_PER_CHAT = 500        # 每个会话最多保留条数


# === 时间戳与工具函数 ===
from datetime import datetime, timezone

def now_iso():
    """返回当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()

def conversation_key(user1, user2):
    """私聊会话的唯一 key：两个用户名按字母序用 : 连接"""
    a, b = (user1, user2) if user1 < user2 else (user2, user1)
    return f"{a}:{b}"
