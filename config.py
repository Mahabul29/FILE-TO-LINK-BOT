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
# Hardcoded default fallback to your channel ID: -1004482213469
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", os.environ.get("BIN_CHANNEL", -1004482213469)))
BIN_CHANNEL = int(os.environ.get("BIN_CHANNEL", LOG_CHANNEL))

# --- Admin Settings ---
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
ADMINS = [OWNER_ID] 

# --- Connection Settings ---
PORT = int(os.environ.get("PORT", "8080"))
FQDN = os.environ.get("FQDN", "filetolink-8klbbde4.b4a.run")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

# --- External Players Configuration ---
PLAYERS = {
    "vlc":       {"package": "org.videolan.vlc",           "label": "ᴠʟᴄ ᴘʟᴀʏᴇʀ"},
    "mx":        {"package": "com.mxtech.videoplayer.ad",  "label": "ᴍx ᴘʟᴀʏᴇʀ"},
    "splayer":   {"package": "com.ttee.leeplayer",         "label": "ꜱᴘʟᴀʏᴇʀ"},
    "playit":    {"package": "com.playit.videoplayer",     "label": "ᴘʟᴀʏɪᴛ"},
    "evaplayer": {"package": "com.evaplayer.app",         "label": "ᴇᴠᴀᴘʟᴀʏᴇʀ"},
}

# --- Streamtape (auto upload + auto restore) ---
# Get both from Streamtape -> Account Settings -> API login / key
STREAMTAPE_LOGIN = os.environ.get("STREAMTAPE_LOGIN", "")
STREAMTAPE_KEY = os.environ.get("STREAMTAPE_KEY", "")
# Optional Streamtape folder ID where the bot puts files
STREAMTAPE_FOLDER = os.environ.get("STREAMTAPE_FOLDER", "")
# How often (minutes) the bot checks that your Streamtape files still exist
HEAL_INTERVAL_MIN = max(5, int(os.environ.get("HEAL_INTERVAL_MIN", "60")))
# Give up on one upload after this many minutes
UPLOAD_TIMEOUT_MIN = int(os.environ.get("UPLOAD_TIMEOUT_MIN", "120"))
# How many files may upload to Streamtape at the same time
UPLOAD_PARALLEL = max(1, int(os.environ.get("UPLOAD_PARALLEL", "2")))

# --- DoodStream (auto upload + auto restore) ---
# Get the API key from DoodStream -> Account Settings -> API
DOODSTREAM_KEY = os.environ.get("DOODSTREAM_KEY", "")
# Domain used for DoodStream page/embed links (DoodStream changes domains often)
DOODSTREAM_DOMAIN = os.environ.get("DOODSTREAM_DOMAIN", "doodstream.com").strip().replace("https://", "").strip("/")

# --- Mixdrop (auto upload + auto restore) ---
# Mixdrop -> Account -> API: your account e-mail and API key
MIXDROP_EMAIL = os.environ.get("MIXDROP_EMAIL", "").strip()
MIXDROP_KEY = os.environ.get("MIXDROP_KEY", "").strip()
# Domain used for Mixdrop page/embed links (Mixdrop changes domains sometimes)
MIXDROP_DOMAIN = os.environ.get("MIXDROP_DOMAIN", "mixdrop.ag").strip().replace("https://", "").strip("/")

# How /sv/<id>, /dv/<id> and /mv/<id> (the direct-video link for apps) serves the Streamtape file:
#   redirect = send the app straight to Streamtape's video URL (no bot bandwidth)
#   proxy    = the bot streams it through itself (use this if redirect does not play)
STREAM_MODE = os.environ.get("STREAM_MODE", "proxy").lower()
