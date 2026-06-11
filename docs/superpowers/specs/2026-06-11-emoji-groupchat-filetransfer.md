# 聊天软件 — Emoji 面板 + 群聊 + 文件传输

**日期**: 2026-06-11
**状态**: 已确认

---

## 1. 目标

分三个子系统逐步增强聊天软件功能，均支持公聊/群聊/私聊三种场景。

## 2. Emoji 面板

### 2.1 范围

纯客户端改动，不动服务端和协议。emoji 即 Unicode 字符，和文字一起混排在聊天气泡中。

### 2.2 UI

- 输入框右侧新增 emoji 按钮（😀），紧挨发送按钮左侧
- 点击弹出 `tkinter.Toplevel` 面板，6 列 x 9 行网格，共 54 个常用 emoji
- 每个 emoji 为一个 Button，字号 16，点击后插入到 `entry_msg` 光标位置
- 面板有置顶（`topmost`）特性，点击空白处自动关闭

### 2.3 emoji 列表

固定列表，定义在 client.py 中：
```python
EMOJI_LIST = [
    "😀", "😂", "🤣", "😅", "😊", "😍",
    "🤔", "😐", "😢", "😠", "😨", "🤯",
    "👍", "👎", "👏", "🙏", "💪", "🤝",
    "❤️", "🔥", "⭐", "🎉", "✨", "💡",
    "🍔", "🍕", "☕", "🍺", "🎂", "🌈",
    "🚗", "✈️", "🏠", "🌍", "⏰", "📅",
    "📎", "🔒", "💻", "📱", "🎵", "📸",
    "🐱", "🐶", "🎮", "⚽", "🎬", "🎯",
    "✅", "❌", "⚠️", "🔍", "📝", "💬",
]
```

### 2.4 不变的内容

气泡渲染（`_render_bubble`）、协议、服务端均不修改。

## 3. 群聊

### 3.1 概念

- **大厅（public）**：所有用户自动参与，行为不变
- **群聊（group）**：用户创建/加入/退出的独立聊天空间
- **私聊（private）**：现有 1v1 聊天，不变

### 3.2 数据库

新增两张表：

```sql
CREATE TABLE groups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE group_members (
    group_id  INTEGER,
    username  TEXT,
    joined_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (group_id, username)
);
```

消息 `chat_key` 规则：
- 公聊 → `"public"`
- 群聊 → `"group:3"` (group:<id>)
- 私聊 → `"alice:bob"` (不变)

### 3.3 服务端

| 功能 | 方法 | 说明 |
|------|------|------|
| 创建群 | `_handle_create_group` | INSERT groups + 创建者自动加入 |
| 加入群 | `_handle_join_group` | INSERT group_members |
| 退出群 | `_handle_leave_group` | DELETE group_members |
| 解散群 | `_handle_delete_group` | 仅创建者可操作，DELETE groups + members |
| 群成员列表 | `_handle_group_users` | SELECT group_members WHERE group_id=? |
| 群历史 | 复用 `_handle_get_history` | target = "group:3" |
| 群消息 | 复用 `_handle_broadcast`/`_handle_private` 模式 | 新增 `_handle_group_message`，聊天 key = "group:3" |

新增协议消息类型：
```
TYPE_CREATE_GROUP = "create_group"  # → {"name": "..."}
TYPE_JOIN_GROUP   = "join_group"    # → {"group_id": 3}
TYPE_LEAVE_GROUP  = "leave_group"   # → {"group_id": 3}
TYPE_DELETE_GROUP = "delete_group"  # → {"group_id": 3}
TYPE_GROUP_USERS  = "group_users"   # → {"group_id": 3}
TYPE_GROUP_MSG    = "group_msg"     # → {"group_id": 3, "content": "...", "timestamp": "..."}
```

`_handle_login` 响应新增 `groups` 字段：用户加入的群列表 `[{id, name, members}]`。

### 3.4 客户端

左侧面板改为三层树形结构：

```
┌──────────────────┐
│  搜索            │
├──────────────────┤
│ ★ 公聊大厅       │
│ ▼ 群聊           │
│    班级群         │
│    兴趣小组       │
│ ▼ 联系人         │
│    alice ●       │
│    bob           │
├──────────────────┤
│ [+创建群]        │
└──────────────────┘
```

- 群聊节点可展开/折叠
- 右键群名弹出菜单：退出群 / 解散群（创建者可见）/ 查看成员
- [+创建群] 按钮弹对话框输入群名
- 群成员在线状态：● 绿色 / ○ 灰色
- 搜索过滤支持群名和联系人

## 4. 文件传输

### 4.1 架构

```
客户端 A                    服务端                    客户端 B
   │                         │                         │
   ├─ file_send ────────────►│                        │
   │  (filename, size,       │                         │
   │   receiver=B)           │                         │
   │                         ├─ file_notify ──────────►│
   │                         │  (file_id, filename,     │
   │                         │   size, sender=A)        │
   │                         │                         │
   ├─ TCP:9998 ─────────────►│                        │
   │  upload file data       │                         │
   │                         │                         │
   │                         │        ┌─ 下载按钮 ◄────┤
   │                         │        │                │
   │                         │◄─ TCP:9998 ─────────────┤
   │                         │   download file data     │
```

### 4.2 服务端文件端口

- 主聊天端口 9999 不变
- 新增文件端口 9998，处理上传/下载请求
- `files/` 目录存储文件，文件名 = `file_id`（UUID）
- 上传完成后在主线程通过聊天通道发 `file_notify`
- 文件元数据存在 SQLite：

```sql
CREATE TABLE files (
    file_id   TEXT PRIMARY KEY,
    filename  TEXT NOT NULL,
    size      INTEGER NOT NULL,
    sender    TEXT NOT NULL,
    receiver  TEXT NOT NULL,
    chat_key  TEXT NOT NULL,
    timestamp TEXT DEFAULT (datetime('now'))
);
```

### 4.3 协议

文件传输走聊天通道（9999）：
```json
// 发送方 → 服务端
{"type": "file_send", "receiver": "bob", "filename": "photo.png", "size": 12345}

// 服务端 → 发送方 (响应)
{"type": "response", "status": "ok", "file_id": "uuid..."}

// 服务端 → 接收方
{"type": "file_notify", "file_id": "uuid...", "filename": "photo.png", "size": 12345, "sender": "alice"}

// 接收方 → 服务端 (请求下载)
{"type": "file_download", "file_id": "uuid..."}
```

文件通道（9998）协议：简单二进制流
- 上传：发送方连接 9998 → 发送 `file_id\n` → 发送文件数据 → 服务端存盘
- 下载：接收方连接 9998 → 发送 `file_id\n` → 服务端返回文件数据

### 4.4 客户端 UI

- 输入框弹出菜单或附件按钮（📎），点击弹出菜单：发送文件 / 表情
- 发送文件 → 系统文件选择对话框 → 上传 → 消息区域显示文件卡片（右侧，绿色）
- 收到文件 → 消息区域显示文件卡片（左侧，白色）
- 文件卡片样式：
  ```
  ┌──────────────────────────────┐
  │ 📄 photo.png                 │
  │ 123 KB                       │
  │ [下载] 已下载 / 下载中 45%   │
  └──────────────────────────────┘
  ```
- 下载时有进度条
- 文件保存到 `downloads/` 目录（客户端本地）

## 5. 不改动的

- 登录/注册流程（LoginWindow）
- 现有私聊机制
- SQLite 持久化方案
- Python 标准库约束（无第三方依赖）

## 6. 测试要点

### Emoji
1. 点击 emoji 按钮弹出面板
2. 点击 emoji 插入到输入框
3. emoji 在气泡中正常显示
4. emoji + 文字混排不换行错乱

### 群聊
1. 创建群成功，创建者自动加入
2. 加入/退出群正常
3. 群消息广播给群内所有在线成员
4. 群历史持久化，重启不丢失
5. 解散群后成员不可再发消息

### 文件传输
1. 发送文件给在线用户，接收方收到通知
2. 下载文件成功，内容完整
3. 大文件（>10MB）分块传输不阻塞聊天
4. 接收方离线时发送方收到错误提示
5. 进度条正确显示
