import asyncio
import logging
import os

# Old files that crash the bot on start (stale copies left on the server).
# They are removed automatically before the plugins are loaded.
_ROOT = os.path.dirname(os.path.abspath(__file__))
for _stale in ("plugins/channel_handler.py", "plugins/dl.py", "web/stream.py"):
    _path = os.path.join(_ROOT, _stale)
    if _stale == "plugins/dl.py" and not os.path.exists(os.path.join(_ROOT, "web", "dl.py")):
        continue  # only drop it once web/dl.py is in place
    try:
        os.remove(_path)
        print(f"🧹 removed stale file: {_stale}")
    except FileNotFoundError:
        pass
    except Exception as _e:
        print(f"⚠️ could not remove {_stale}: {_e}")

from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN, BIN_CHANNEL, HEAL_ENABLED, FQDN
from web.server import web_server
from utils import streamtape

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="FileToLinkBot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins")
        )

    async def start(self):
        await super().start()
        try:
            await self.get_chat(BIN_CHANNEL)
            print("✅ Connection to Bin Channel Verified")
        except Exception as e:
            print(f"❌ Bin Channel Error: {e}")

        self.runner = await web_server(self)
        print("✅ Web Server Started")
        if not FQDN:
            print("⚠️ FQDN is not set: add your bot-hosting.net domain in Environment")

        self.heal_task = None
        if streamtape.enabled and HEAL_ENABLED:
            self.heal_task = asyncio.create_task(streamtape.heal_loop())
            print("✅ Streamtape auto-restore started")
        else:
            print("ℹ️ Streamtape auto-restore off (no keys, or HEAL_ENABLED=false)")


    async def stop(self, *args):
        t = getattr(self, "heal_task", None)
        if t:
            t.cancel()
        await super().stop()
        await self.runner.cleanup()
        print("🛑 Bot Stopped")

