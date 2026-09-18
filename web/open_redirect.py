import logging
import urllib.parse
from aiohttp import web
from config import BIN_CHANNEL, FQDN, PLAYERS

logger = logging.getLogger(__name__)


async def open_in_player(request):
    """
    GET /open/{player}/{file_id}
    Redirects into intent:// URL including the sanitized file_name parameter.
    """
    player = request.match_info.get("player")
    file_id = request.match_info.get("file_id")

    info = PLAYERS.get(player)
    if not info:
        return web.Response(text="Unknown player", status=404)

    package = info["package"]
    label = info["label"]

    bot_client = request.app.get("bot_client")
    file_name = "video.mp4"

    if bot_client and file_id:
        try:
            msg = await bot_client.get_messages(int(BIN_CHANNEL), int(file_id))
            media = msg.document or msg.video or msg.audio or msg.photo
            if media:
                file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
        except Exception as e:
            logger.error(f"Error fetching filename for intent redirect: {e}")

    safe_name = urllib.parse.quote(file_name)

    clean_fqdn = FQDN.replace("https://", "").replace("http://", "").strip().rstrip("/")
    if not clean_fqdn or clean_fqdn == "localhost":
        clean_fqdn = "example.com"

    stream_url_bare = f"{clean_fqdn}/stream/{file_id}/{safe_name}"
    fallback_url = f"https://play.google.com/store/apps/details?id={package}"

    intent_url = (
        f"intent://{stream_url_bare}#Intent;"
        f"package={package};type=video/*;scheme=https;"
        f"S.title={safe_name};"
        f"S.browser_fallback_url={fallback_url};"
        f"end"
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{file_name}</title>
    <meta http-equiv="refresh" content="0;url={intent_url}">
    <script>window.location.href = "{intent_url}";</script>
    <style>
        body {{
            background: #080c12;
            color: #e8f0f8;
            font-family: sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            text-align: center;
            padding: 20px;
            box-sizing: border-box;
        }}
        a {{ color: #2481cc; }}
    </style>
</head>
<body>
    <div>
        <p>Opening in {label}...</p>
        <p><a href="{intent_url}">Tap here if it doesn't open automatically</a></p>
    </div>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html", charset="utf-8")
    
