from aiohttp import web
from config import FQDN

_PLAYERS = {
    "vlc": ("org.videolan.vlc", "VLC"),
    "mx": ("com.mxtech.videoplayer.ad", "MX Player"),
}


async def open_in_player(request):
    """
    GET /open/{player}/{file_id}
    A plain https:// page (valid for Telegram inline buttons) that immediately
    redirects into the intent:// URL for the chosen external player.
    """
    player = request.match_info.get("player")
    file_id = request.match_info.get("file_id")

    info = _PLAYERS.get(player)
    if not info:
        return web.Response(text="Unknown player", status=404)
    package, label = info

    clean_fqdn = FQDN.replace("https://", "").replace("http://", "").rstrip("/")
    stream_url_bare = f"{clean_fqdn}/stream/{file_id}"
    fallback_url = f"https://play.google.com/store/apps/details?id={package}"

    intent_url = (
        f"intent://{stream_url_bare}#Intent;"
        f"package={package};type=video/*;scheme=https;"
        f"S.browser_fallback_url={fallback_url};"
        f"end"
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
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
        <p>Opening in {label}…</p>
        <p><a href="{intent_url}">Tap here if it doesn't open automatically</a></p>
    </div>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")
  
