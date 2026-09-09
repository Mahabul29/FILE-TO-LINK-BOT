import os

# --- Core Bot Credentials ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "") 
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# --- Database ---
DATABASE_URI = os.environ.get("DATABASE_URI", os.environ.get("MONGO_URI", ""))
DATABASE_NAME = os.environ.get("DATABASE_NAME", os.environ.get("DB_NAME", "TelegramBot"))

# Aliases to fix module import mismatches across files
MONGO_URI = DATABASE_URI
DB_NAME = DATABASE_NAME

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

# --- External Players Configuration ---
PLAYERS = {
    "ᴠʟᴄ ᴘʟᴀʏᴇʀ":     {"package": "org.videolan.vlc",           "label": "ᴠʟᴄ ᴘʟᴀʏᴇʀ"},
    "ᴍx ᴘʟᴀʏᴇʀ":      {"package": "com.mxtech.videoplayer.ad",  "label": "ᴍx ᴘʟᴀʏᴇʀ"},
    "sᴘʟᴀʏᴇʀ": {"package": "com.ttee.leeplayer",          "label": "ꜱᴘʟᴀʏᴇʀ"},
    "ᴘʟᴀʏɪᴛ":  {"package": "com.playit.videoplayer",      "label": "ᴘʟᴀʏɪᴛ"},
}
