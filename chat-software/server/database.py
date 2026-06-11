"""
数据库层：SQLite 连接管理、建表、所有 CRUD 操作
"""

import sqlite3
import os

from common.protocol import MAX_MESSAGES_PER_CHAT

DB_FILE = "chat.db"


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        os.makedirs("files", exist_ok=True)

    def _create_tables(self):
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
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                username TEXT,
                contact  TEXT,
                added_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (username, contact)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_id   TEXT PRIMARY KEY,
                filename  TEXT NOT NULL,
                size      INTEGER NOT NULL,
                sender    TEXT NOT NULL,
                receiver  TEXT NOT NULL,
                chat_key  TEXT NOT NULL,
                timestamp TEXT DEFAULT (datetime('now'))
            )
        """)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ========================
    #  Users
    # ========================
    def load_users(self):
        rows = self.conn.execute("SELECT username, password FROM users").fetchall()
        return {r[0]: r[1] for r in rows}

    def register_user(self, username, password):
        self.conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, password),
        )
        self.conn.commit()

    def search_users(self, query, exclude):
        rows = self.conn.execute(
            "SELECT username FROM users WHERE username LIKE ? AND username != ? LIMIT 20",
            (f"%{query}%", exclude),
        ).fetchall()
        return [r[0] for r in rows]

    # ========================
    #  Messages
    # ========================
    def add_message(self, chat_key, sender, content, timestamp):
        self.conn.execute(
            "INSERT INTO messages (chat_key, sender, content, timestamp) VALUES (?, ?, ?, ?)",
            (chat_key, sender, content, timestamp),
        )
        self.conn.execute("""
            DELETE FROM messages WHERE chat_key = ? AND id NOT IN (
                SELECT id FROM messages WHERE chat_key = ? ORDER BY id DESC LIMIT ?
            )
        """, (chat_key, chat_key, MAX_MESSAGES_PER_CHAT))
        self.conn.commit()

    def get_history(self, chat_key, limit=50):
        rows = self.conn.execute(
            "SELECT sender, content, timestamp FROM messages "
            "WHERE chat_key = ? ORDER BY id DESC LIMIT ?",
            (chat_key, limit),
        ).fetchall()
        return [{"sender": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]

    def get_conversations(self, username):
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
                partners.append((partner, last[0] if last else ""))
        partners.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in partners]

    # ========================
    #  Groups
    # ========================
    def create_group(self, name, created_by):
        cur = self.conn.execute(
            "INSERT INTO groups (name, created_by) VALUES (?, ?)", (name, created_by)
        )
        gid = cur.lastrowid
        self.conn.execute(
            "INSERT INTO group_members (group_id, username) VALUES (?, ?)", (gid, created_by)
        )
        self.conn.commit()
        return gid

    def join_group(self, gid, username):
        self.conn.execute(
            "INSERT INTO group_members (group_id, username) VALUES (?, ?)", (gid, username)
        )
        self.conn.commit()

    def leave_group(self, gid, username):
        self.conn.execute(
            "DELETE FROM group_members WHERE group_id=? AND username=?", (gid, username)
        )
        self.conn.commit()

    def delete_group(self, gid):
        self.conn.execute("DELETE FROM group_members WHERE group_id=?", (gid,))
        self.conn.execute("DELETE FROM groups WHERE id=?", (gid,))
        self.conn.commit()

    def is_group_member(self, gid, username):
        row = self.conn.execute(
            "SELECT 1 FROM group_members WHERE group_id=? AND username=?", (gid, username)
        ).fetchone()
        return row is not None

    def get_group_info(self, gid):
        return self.conn.execute(
            "SELECT id, name, created_by FROM groups WHERE id=?", (gid,)
        ).fetchone()

    def get_group_members(self, gid):
        rows = self.conn.execute(
            "SELECT username FROM group_members WHERE group_id=?", (gid,)
        ).fetchall()
        return [r[0] for r in rows]

    def get_user_groups(self, username):
        gids = self.conn.execute(
            "SELECT group_id FROM group_members WHERE username=?", (username,)
        ).fetchall()
        groups = []
        for (gid,) in gids:
            grp = self.get_group_info(gid)
            if grp:
                groups.append({
                    "id": grp[0], "name": grp[1], "created_by": grp[2],
                    "members": self.get_group_members(gid),
                })
        return groups

    # ========================
    #  Files
    # ========================
    def insert_file(self, file_id, filename, size, sender, receiver, chat_key):
        self.conn.execute(
            "INSERT INTO files (file_id, filename, size, sender, receiver, chat_key) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, filename, size, sender, receiver, chat_key),
        )
        self.conn.commit()

    def update_file_size(self, file_id, size):
        self.conn.execute("UPDATE files SET size=? WHERE file_id=?", (size, file_id))
        self.conn.commit()

    def get_file_info(self, file_id):
        return self.conn.execute(
            "SELECT receiver, filename, size, sender, chat_key FROM files WHERE file_id=?",
            (file_id,),
        ).fetchone()

    # ========================
    #  Contacts
    # ========================
    def get_contacts(self, username):
        rows = self.conn.execute(
            "SELECT contact FROM contacts WHERE username=? ORDER BY added_at", (username,)
        ).fetchall()
        return [r[0] for r in rows]

    def add_contact(self, username, contact):
        exist = self.conn.execute(
            "SELECT 1 FROM contacts WHERE username=? AND contact=?", (username, contact)
        ).fetchone()
        if exist:
            return False
        self.conn.execute(
            "INSERT INTO contacts (username, contact) VALUES (?, ?)", (username, contact)
        )
        self.conn.commit()
        return True
