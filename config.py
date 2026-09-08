import os
import sys
import logging
from urllib.parse import quote_plus
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from motor.motor_asyncio import AsyncIOMotorClient

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Core Bot Credentials ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "") 
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# --- Database ---
DATABASE_URI = os.environ.get("DATABASE_URI", "")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "TelegramBot")

# --- Channel Configuration ---
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", 0))
BIN_CHANNEL = int(os.environ.get("BIN_CHANNEL", 0)) 

# --- Admin Settings ---
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
ADMINS = [OWNER_ID] 

# --- Connection Settings ---
PORT = int(os.environ.get("PORT", "8080"))
FQDN = os.environ.get("FQDN", "localhost")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

# --- External Players ---
PLAYERS = {
    "vlc":     {"package": "org.videolan.vlc",           "label": "VLC"},
    "mx":      {"package": "com.mxtech.videoplayer.ad",  "label": "MX Player"},
    "splayer": {"package": "com.ttee.leeplayer",          "label": "SPlayer"},
    "playit":  {"package": "com.playit.videoplayer",      "label": "PLAYit"},
}

# --- Database Client ---
if DATABASE_URI:
    db_client = AsyncIOMotorClient(DATABASE_URI)
    db = db_client[DATABASE_NAME]
else:
    db_client = None
    db = None

# --- Telegram Client ---
app = Client(
    "FileStreamBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- Helper Functions ---
def get_media_file(message: Message):
    """Extracts media object from a message."""
    return message.video or message.document or message.audio or message.voice or None

def build_player_links(stream_url: str) -> list:
    """Generates intent/scheme links for external Android video players."""
    buttons = []
    
    # VLC
    vlc_url = f"vlc://{stream_url}"
    buttons.append(InlineKeyboardButton("VLC", url=vlc_url))
    
    # MX Player
    mx_url = f"intent:{stream_url}#Intent;package={PLAYERS['mx']['package']};type=video/*;end"
    buttons.append(InlineKeyboardButton("MX Player", url=mx_url))

    # SPlayer
    sp_url = f"intent:{stream_url}#Intent;package={PLAYERS['splayer']['package']};type=video/*;end"
    buttons.append(InlineKeyboardButton("SPlayer", url=sp_url))

    # PLAYit
    playit_url = f"intent:{stream_url}#Intent;package={PLAYERS['playit']['package']};type=video/*;end"
    buttons.append(InlineKeyboardButton("PLAYit", url=playit_url))
    
    # Grid formatting (2 buttons per row)
    return [buttons[i:i + 2] for i in range(0, len(buttons), 2)]

# --- Web Server Handlers ---
routes = web.RouteTableDef()

@routes.get("/")
async def root_route_handler(request):
    return web.json_response({"status": "running", "bot": BOT_USERNAME})

@routes.get("/watch/{log_id}")
async def stream_handler(request):
    """Handles HTTP video streaming with Byte-Range support."""
    try:
        log_id = int(request.match_info["log_id"])
        message = await app.get_messages(BIN_CHANNEL, log_id)
        media = get_media_file(message)
        
        if not media:
            return web.Response(status=404, text="Media File Not Found")
        
        file_size = media.file_size
        range_header = request.headers.get("Range")
        
        if range_header:
            bytes_unit, src_range = range_header.split("=")
            start, end = src_range.split("-")
            start = int(start)
            end = int(end) if end else file_size - 1
        else:
            start = 0
            end = file_size - 1

        length = end - start + 1
        headers = {
            "Content-Type": getattr(media, "mime_type", "video/mp4"),
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Disposition": f'attachment; filename="{getattr(media, "file_name", "file.mp4")}"'
        }

        response = web.StreamResponse(status=206 if range_header else 200, headers=headers)
        await response.prepare(request)

        async for chunk in app.stream_media(message, offset=start, limit=length):
            await response.write(chunk)

        return response
    except Exception as e:
        logger.error(f"Error streaming file: {e}")
        return web.Response(status=500, text="Internal Server Error")

# --- Telegram Bot Handlers ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    await message.reply_text(
        f"**Hello {message.from_user.first_name}!**\n\n"
        "Send me any file or video, and I will generate direct streaming links and external player links for you."
    )

@app.on_message((filters.private & (filters.document | filters.video | filters.audio)) & ~filters.forwarded)
async def media_handler(client: Client, message: Message):
    media = get_media_file(message)
    if not media:
        return

    # Forward message to storage channel
    log_msg = await message.forward(chat_id=BIN_CHANNEL)
    
    # Construct base streaming URL
    protocol = "https" if FQDN.startswith("https") else "http"
    base_domain = FQDN if FQDN.startswith("http") else f"{protocol}://{FQDN}"
    
    if PORT not in (80, 443) and not FQDN.startswith("http"):
        base_domain = f"{base_domain}:{PORT}"

    stream_url = f"{base_domain}/watch/{log_msg.id}"
    
    # Generate Player Buttons
    player_buttons = build_player_links(stream_url)
    player_buttons.insert(0, [InlineKeyboardButton("Fast Download / Direct Stream", url=stream_url)])
    
    reply_markup = InlineKeyboardMarkup(player_buttons)

    await message.reply_text(
        text=(
            f"**File Name:** `{getattr(media, 'file_name', 'Media File')}`\n"
            f"**File Size:** `{round(media.file_size / (1024 * 1024), 2)} MB`\n\n"
            "**Stream / Download Links:**"
        ),
        reply_markup=reply_markup,
        quote=True
    )

# --- Web App Runner ---
async def start_web_server():
    server = web.Application()
    server.add_routes(routes)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Web server started on port {PORT}")

# --- Main Entry Point ---
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    
    # Start Web App
    loop.create_task(start_web_server())
    
    # Start Pyrogram Bot
    logger.info("Starting Telegram Bot...")
    app.run()
  
