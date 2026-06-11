"""
消息处理器：每个函数处理一种消息类型
"""

import uuid

from common.protocol import (
    TYPE_REGISTER, TYPE_LOGIN, TYPE_BROADCAST, TYPE_PRIVATE,
    TYPE_GET_USERS, TYPE_RESPONSE,
    TYPE_GET_HISTORY, TYPE_HISTORY,
    TYPE_CREATE_GROUP, TYPE_JOIN_GROUP, TYPE_ADD_MEMBER,
    TYPE_LEAVE_GROUP, TYPE_DELETE_GROUP, TYPE_GROUP_USERS, TYPE_GROUP_MSG,
    TYPE_FILE_SEND, TYPE_FILE_DOWNLOAD,
    TYPE_SEARCH_USERS, TYPE_ADD_CONTACT,
    MAX_HISTORY,
    STATUS_OK, STATUS_ERROR,
    make_message, make_response,
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
        server.clients[username]["addr"] = msg.get("_addr")
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
    username = server._current_user(sock)
    if not username:
        server._safe_send(sock, make_response(STATUS_ERROR, "请先登录").encode())
        return None
    content = msg.get("content", "")
    if not content.strip():
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
