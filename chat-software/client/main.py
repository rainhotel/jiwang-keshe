"""聊天客户端入口"""
from client.ui.login import LoginWindow
from client.ui.chat import ChatWindow

if __name__ == "__main__":
    login = LoginWindow()
    login.run()

    if login.username and login.nc:
        chat = ChatWindow(
            login.nc, login.username,
            public_history=login._login_public_history,
            conversations=login._login_conversations,
            groups=login._login_groups,
            contacts=login._login_contacts,
        )
        chat.run()
