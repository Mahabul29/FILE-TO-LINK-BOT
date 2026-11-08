import os

# --- Core Bot Credentials ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "") 
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# --- Database ---
DATABASE_URI = os.environ.get("DATABASE_URI", os.environ.get("DATABASE_URL", os.environ.get("MONGO_URI", "")))
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
# Your bot-hosting.net domain, no https://. All links are built from it.
FQDN = os.environ.get("FQDN", "").replace("https://", "").replace("http://", "").strip().strip("/")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

# Domain written into links people see (/s/, /sv/).
# FQDN stays the address that Streamtape downloads from when uploading
# (it must point at THIS server). If PUBLIC_FQDN is empty, links use FQDN as before.
PUBLIC_FQDN = os.environ.get("PUBLIC_FQDN", "").strip() or FQDN
# Set HEAL_ENABLED=false on a server that should NOT auto re-upload deleted files.
HEAL_ENABLED = os.environ.get("HEAL_ENABLED", "true").strip().lower() not in ("false", "0", "no")

# --- Streamtape (auto upload + auto restore) ---
# Get both from Streamtape -> Account Settings -> API login / key
STREAMTAPE_LOGIN = os.environ.get("STREAMTAPE_LOGIN", "").strip()
STREAMTAPE_KEY = os.environ.get("STREAMTAPE_KEY", "").strip()
# Optional Streamtape folder ID where the bot puts files
STREAMTAPE_FOLDER = os.environ.get("STREAMTAPE_FOLDER", "").strip()
# How often (minutes) the bot checks that your Streamtape files still exist
HEAL_INTERVAL_MIN = max(5, int(os.environ.get("HEAL_INTERVAL_MIN", "10")))
# Give up on one upload after this many minutes
UPLOAD_TIMEOUT_MIN = int(os.environ.get("UPLOAD_TIMEOUT_MIN", "120"))
# How many files may upload to Streamtape at the same time
UPLOAD_PARALLEL = max(1, int(os.environ.get("UPLOAD_PARALLEL", "2")))

# How /sv/<id> (the direct-video link for apps) serves the Streamtape file:
#   redirect = send the app straight to Streamtape's video URL (no bot bandwidth)
#   proxy    = the bot streams it through itself (use this if redirect does not play)
STREAM_MODE = os.environ.get("STREAM_MODE", "proxy").lower()


# --- LuluStream (auto upload + auto restore, works together with Streamtape) ---
# Get the key from LuluStream -> Account Settings -> API key
LULUSTREAM_KEY = os.environ.get("LULUSTREAM_KEY", "").strip()
# Optional LuluStream folder ID (fld_id) where the bot puts files
LULUSTREAM_FOLDER = os.environ.get("LULUSTREAM_FOLDER", "").strip()
# Domain used for watch/embed pages
LULUSTREAM_DOMAIN = os.environ.get("LULUSTREAM_DOMAIN", "lulustream.com").replace("https://", "").replace("http://", "").strip().strip("/")
# true = also upload OLD files (sent before LuluStream was added) to LuluStream in the background
LULUSTREAM_BACKFILL = os.environ.get("LULUSTREAM_BACKFILL", "false").strip().lower() in ("true", "1", "yes")
# LuluStream API address
LULUSTREAM_API = os.environ.get("LULUSTREAM_API", "https://lulustream.com/api").strip().rstrip("/")

# Name shown in the bot message and button for the second host (e.g. LuluStream)
LULUSTREAM_LABEL = os.environ.get("LULUSTREAM_LABEL", "LuluStream").strip() or "LuluStream"
