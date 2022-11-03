import requests
import re
import irc
import ssl
import irc.bot
import irc.strings
import irc.connection
import os

IRC_SERVER = os.environ.get("IRC_SERVER", "irc.hackint.org")
IRC_CHANNEL = os.environ.get("IRC_CHANNEL", "#tikoff")
IRC_USER = os.environ.get("IRC_USER", "TikOffArchive")


def archive_vid(vid_id):
    requests.post(
        "https://archive-tiktok-worker.blazelight.dev/add_work",
        json={"video_ids": [vid_id]},
    )


def archive_user(username):
    requests.post(
        "https://archive-tiktok-worker.blazelight.dev/add_work",
        json={"users": [username]},
    )


class TikOffBot(irc.bot.SingleServerIRCBot):
    def __init__(self, channel, nickname, server, port=6697):
        ssl_factory = irc.connection.Factory(wrapper=ssl.wrap_socket)
        irc.bot.SingleServerIRCBot.__init__(
            self, [(server, port)], nickname, nickname, connect_factory=ssl_factory
        )
        self.channel = channel

    def on_welcome(self, c, e):
        print("Received IRC welcome ")
        c.join(self.channel)

    def on_join(self, c, e):
        print(e)

    def on_pubmsg(self, c, event):
        message = event.arguments[0]
        msg_segments = message.split()

        if msg_segments[0].startswith("!archive"):
            for arg in msg_segments[1:]:
                if "vm.tiktok.com" in arg:
                    # Get redirected target url
                    r = requests.get(arg)
                    arg = r.url

                if vid_match := re.search(r"(\d{19})", arg):
                    vid_id = vid_match[0]
                    archive_vid(vid_id)
                    c.privmsg(self.channel, f"Archiving video ID {vid_id}")
                elif username_match := re.search(
                    r"@(?!.*\.\.)(?!.*\.$)[^\W][\w.]{2,24}", arg
                ):
                    username = username_match[0]
                    archive_user(username)
                    c.privmsg(self.channel, f"Archiving username {username}")
                else:
                    print(f"Did not understand {arg=}")

    def on_privmsg(self, c, e):
        print(e)


print(IRC_CHANNEL, IRC_USER, IRC_SERVER)
bot = TikOffBot(IRC_CHANNEL, IRC_USER, IRC_SERVER)
bot.start()
