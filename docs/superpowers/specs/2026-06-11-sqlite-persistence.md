# 聊天软件 SQLite 持久化

**日期**: 2026-06-11
**状态**: 已确认

---

## 1. 目标

将用户数据和消息历史的存储从 JSON 文件替换为 SQLite 数据库，解决 JSON 方案的全量读写性能瓶颈和多线程安全隐患。

## 2. 数据库设计

### 2.1 文件

`chat-software/chat.db`，启动时自动创建，启用 WAL 模式。

### 2.2 表结构

```sql
CREATE TABLE IF NOT EXISTS users (
    username    TEXT PRIMARY KEY,
    password    TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_key  TEXT NOT NULL,       -- "public" 或 "alice:bob"
    sender    TEXT NOT NULL,
    content   TEXT NOT NULL,
    timestamp TEXT NOT NULL         -- ISO 格式 (UTC)
);

CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_key, id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(chat_key, timestamp);
```

### 2.3 消息数量限制

每个 `chat_key` 保留最近 500 条消息。插入新消息后，按 `id` 升序删除超出部分：

```sql
DELETE FROM messages WHERE chat_key = ? AND id NOT IN (
    SELECT id FROM messages WHERE chat_key = ? ORDER BY id DESC LIMIT 500
);
```

## 3. 服务端改动

### 3.1 初始化

- 打开 SQLite 连接，执行 `PRAGMA journal_mode=WAL`
- 执行建表语句
- `self.clients` 字典保留，仅存运行时状态 `{"addr", "socket"}`，不再存密码
- 移除 `_load_users`、`_save_users`、`_load_messages`、`_save_messages` 方法
- 移除 `self.messages`（消息数组）

### 3.2 注册

`_handle_register` → `INSERT INTO users` + 发送响应，不维护 clients 中的密码字段。

### 3.3 登录

`_handle_login` → 先从 `users` 表查出密码验证，再查 `clients` 字典检查在线状态。

### 3.4 发消息

`_add_message` → `INSERT INTO messages` + 淘汰旧消息。不再维护 `self.messages`。

### 3.5 历史查询

`_handle_get_history` → `SELECT sender, content, timestamp FROM messages WHERE chat_key = ? ORDER BY id DESC LIMIT ?`

### 3.6 会话列表

`_get_conversations_for_user` → `SELECT DISTINCT chat_key FROM messages WHERE chat_key != 'public' AND (chat_key LIKE ? OR chat_key LIKE ?)`，在应用层解析出对方用户名。

### 3.7 关闭

`shutdown` → `self.conn.close()`。

### 3.8 并发

单连接 + `self.lock`（WAL 模式下读不阻塞写，但保持现有模型简单）。

## 4. 不改动的文件

- `chat-software/common.py` — 协议常量不变
- `chat-software/client.py` — 客户端完全不动
- `chat-software/requirements.txt` — 无新增依赖（sqlite3 是标准库）

## 5. 测试要点

1. 服务端首次启动自动创建 chat.db
2. 服务端重启后用户和消息不丢失
3. 新用户注册后可直接登录
4. 每个会话消息上限 500 条正常淘汰
5. WAL 模式下多线程并发写入不报错
6. 客户端功能不受影响（协议不变）
