"""聊天服务端入口"""
from server.database import Database
from server.server import Server

if __name__ == "__main__":
    db = Database()
    srv = Server(db)
    srv.start()
