import asyncio
import logging
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN, BIN_CHANNEL
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

        self.heal_task = None
        if streamtape.enabled:
            self.heal_task = asyncio.create_task(streamtape.heal_loop())
            print("✅ Streamtape auto-restore started")
        else:
            print("ℹ️ Streamtape disabled (set STREAMTAPE_LOGIN and STREAMTAPE_KEY to enable)")

    async def stop(self, *args):
        if getattr(self, "heal_task", None):
            self.heal_task.cancel()
        await super().stop()
        await self.runner.cleanup()
        print("🛑 Bot Stopped")
        
