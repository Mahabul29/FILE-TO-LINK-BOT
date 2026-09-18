import asyncio
import logging
from urllib.parse import quote
from aiohttp import web
from config import BIN_CHANNEL, FQDN, PLAYERS
from database.settings_db import get_active_player

logger = logging.getLogger(__name__)

CHUNK_SIZE = 512 * 1024  # Reduced chunk size to 512KB for smoother streaming and lower RAM usage
_STREAM_SEMAPHORE = asyncio.Semaphore(5)


def to_small_caps(text: str) -> str:
    mapping = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ',
        'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ',
        'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ꞯ', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ',
        'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
        'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ꜰ', 'G': 'ɢ',
        'H': 'ʜ', 'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ',
        'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ꞯ', 'R': 'ʀ', 'S': 'ꜱ', 'T': 'ᴛ', 'U': 'ᴜ',
        'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x', 'Y': 'ʏ', 'Z': 'ᴢ'
    }
    return "".join(mapping.get(c, c) for c in text)


def _media_info(media):
    file_name = getattr(media, "file_name", "Unknown File")
    mime_type = getattr(media, "mime_type", "application/octet-stream") or "application/octet-stream"
    file_size = getattr(media, "file_size", 0) or 0
    return file_name, mime_type, file_size


_ICON_VIDEO = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 4 20 12 6 20 6 4"></polygon></svg>'
_ICON_AUDIO = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>'
_ICON_DOC = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>'

_PLAYER_BTN_CLASS = {
    "vlc": "btn-vlc",
    "mx": "btn-mx",
    "splayer": "btn-splayer",
    "playit": "btn-playit",
}


def _type_badge(mime_type):
    if "video" in mime_type:
        return "Video", "#ef6461", _ICON_VIDEO
    if "audio" in mime_type:
        return "Audio", "#3ddc97", _ICON_AUDIO
    return "Document", "#5a7a94", _ICON_DOC


async def _get_media(bot_client, file_id):
    msg = await bot_client.get_messages(int(BIN_CHANNEL), int(file_id))
    if not msg:
        return None, None
    media = msg.document or msg.video or msg.audio or msg.photo
    return msg, media


def _build_ext_player_buttons(clean_fqdn, file_id, file_name, active_player):
    keys = list(PLAYERS.keys()) if active_player == "all" else [active_player]
    keys = [k for k in keys if k in PLAYERS]

    if not keys:
        return ""

    encoded_name = quote(file_name)
    stream_url = f"{clean_fqdn}/stream/{file_id}/{encoded_name}"

    buttons_html = []
    for key in keys:
        info = PLAYERS[key]
        package, label = info["package"], info["label"]
        if "Player" not in label and "player" not in label.lower():
            label = f"{label} Player"

        fallback_url = f"https://play.google.com/store/apps/details?id={package}"
        intent_url = (
            f"intent://{stream_url}#Intent;"
            f"package={package};type=video/*;scheme=https;"
            f"S.title={encoded_name};"
            f"S.browser_fallback_url={fallback_url};"
            f"end"
        )
        css_class = _PLAYER_BTN_CLASS.get(key, "btn-vlc")
        styled_label = to_small_caps(label)
        buttons_html.append(f'<a href="{intent_url}" class="btn {css_class}">{styled_label}</a>')

    rows = ""
    for i in range(0, len(buttons_html), 2):
        pair = buttons_html[i:i + 2]
        rows += f'<div class="ext-buttons">{"".join(pair)}</div>\n'
    return rows


async def video_play(request):
    file_id = request.match_info.get("file_id")
    bot_client = request.app["bot_client"]

    clean_fqdn = FQDN.replace("https://", "").replace("http://", "").rstrip("/")

    try:
        msg, media = await _get_media(bot_client, file_id)
        if not media:
            return web.Response(text="❌ File not found", status=404)

        file_name, mime_type, file_size = _media_info(media)
        size_mb = round(file_size / (1024 * 1024), 2)

        encoded_name = quote(file_name)
        stream_path = f"/stream/{file_id}/{encoded_name}"

        # Detect non-standard web video formats (like MKV)
        is_mkv = file_name.lower().endswith('.mkv')

        if "video" in mime_type:
            file_type, accent, icon_svg = _type_badge(mime_type)
            player_tag = f'''
            <video controls autoplay playsinline preload="metadata">
                <source src="{stream_path}" type="{mime_type}">
                Your browser does not support this video format.
            </video>
            '''
            if is_mkv:
                playable_note = "<p class='warn'>⚠️ <b>MKV Container Detected:</b> Web browsers may fail to play sound or video in MKV files. Use VLC or MX Player below for best playback.</p>"
            else:
                playable_note = ""
        elif "audio" in mime_type:
            file_type, accent, icon_svg = _type_badge(mime_type)
            player_tag = f'''
            <audio controls autoplay preload="metadata">
                <source src="{stream_path}" type="{mime_type}">
                Your browser does not support this audio.
            </audio>
            '''
            playable_note = ""
        else:
            file_type, accent, icon_svg = _type_badge(mime_type)
            player_tag = ""
            playable_note = "<p class='warn'>⚠️ This file format cannot play directly in browser. Download or open in external player below.</p>"

    except Exception as e:
        logger.error(f"File info error: {e}")
        file_name = "Video File"
        mime_type = "unknown"
        size_mb = 0
        file_type, accent, icon_svg = "File", "#5a7a94", _ICON_DOC
        player_tag = ""
        playable_note = "<p class='warn'>⚠️ Could not fetch file info.</p>"
        file_id = request.match_info.get("file_id")
        stream_path = f"/stream/{file_id}/video.mp4"

    download_url = f"https://{clean_fqdn}/dl/{file_id}"

    ext_player_buttons = ""
    active_player = await get_active_player()
    ext_player_buttons = _build_ext_player_buttons(clean_fqdn, file_id, file_name, active_player)

    btn_download_text = to_small_caps("Download")
    btn_copy_text = to_small_caps("Copy Link")
    btn_copied_text = to_small_caps("Copied!")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{file_name}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0b1521;
            color: white;
            font-family: 'DM Mono', monospace;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px 15px 40px;
            min-height: 100vh;
        }}
        .title-row {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 15px;
            max-width: 850px;
            width: 100%;
        }}
        .badge {{
            flex: none;
            width: 38px;
            height: 38px;
            border-radius: 10px;
            background: {accent}22;
            border: 1px solid {accent}55;
            color: {accent};
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .title-text {{
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            font-size: 17px;
            line-height: 1.4;
            word-break: break-word;
            padding-top: 6px;
        }}
        .info-box {{
            background: #112033;
            border: 1px solid #2481cc44;
            border-radius: 12px;
            padding: 12px 16px;
            width: 100%;
            max-width: 850px;
            margin-top: 15px;
            margin-bottom: 15px;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #1e3a55;
            font-size: 13px;
            gap: 10px;
        }}
        .info-row:last-child {{ border-bottom: none; }}
        .info-label {{ color: #7fb3d3; white-space: nowrap; }}
        .info-value {{
            color: #fff;
            font-weight: 500;
            word-break: break-all;
            text-align: right;
        }}
        .type-chip {{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 20px;
            background: {accent}22;
            color: {accent};
            font-weight: 600;
            font-size: 12px;
        }}
        video, audio {{
            width: 100%;
            max-width: 850px;
            border-radius: 10px;
            background: #000;
            margin-bottom: 15px;
        }}
        video {{
            border: 1px solid #2481cc44;
        }}
        .warn {{
            color: #f39c12;
            background: #1a1200;
            border: 1px solid #f39c1266;
            border-radius: 8px;
            padding: 10px 15px;
            margin-bottom: 12px;
            font-size: 13px;
            width: 100%;
            max-width: 850px;
            text-align: center;
        }}
        .top-buttons {{
            display: flex;
            gap: 10px;
            width: 100%;
            max-width: 850px;
            margin-bottom: 20px;
        }}
        .btn {{
            flex: 1;
            padding: 13px 10px;
            color: white;
            text-decoration: none;
            border-radius: 10px;
            font-weight: bold;
            font-size: 14px;
            text-align: center;
            transition: opacity 0.2s;
            cursor: pointer;
            border: none;
            display: inline-block;
        }}
        .btn:hover {{ opacity: 0.85; }}
        .btn-download {{ background: #27ae60; }}
        .btn-copy {{ background: #2481cc; }}
        .copied {{ background: #1a6aaa !important; }}
        .ext-buttons {{
            display: flex;
            gap: 10px;
            width: 100%;
            max-width: 850px;
            margin-bottom: 10px;
        }}
        .btn-vlc {{ background: #e85e00; }}
        .btn-mx {{ background: #1f2937; border: 1px solid #37415155; }}
        .btn-splayer {{ background: #2d7dd2; }}
        .btn-playit {{ background: #d92027; }}
    </style>
</head>
<body>

    <div class="title-row">
        <span class="badge">{icon_svg}</span>
        <span class="title-text">{file_name}</span>
    </div>

    {playable_note}
    {player_tag}

    {ext_player_buttons}

    <div class="info-box">
        <div class="info-row">
            <span class="info-label">📄 File Name</span>
            <span class="info-value">{file_name}</span>
        </div>
        <div class="info-row">
            <span class="info-label">📦 Size</span>
            <span class="info-value">{size_mb} MB</span>
        </div>
        <div class="info-row">
            <span class="info-label">🎞️ Type</span>
            <span class="type-chip">{file_type}</span>
        </div>
        <div class="info-row">
            <span class="info-label">🆔 File ID</span>
            <span class="info-value">{file_id}</span>
        </div>
    </div>

    <div class="top-buttons">
        <a href="{download_url}" class="btn btn-download">{btn_download_text}</a>
        <button class="btn btn-copy" onclick="copyLink()">{btn_copy_text}</button>
    </div>

    <script>
        const downloadUrl = "{download_url}";

        function copyLink() {{
            navigator.clipboard.writeText(downloadUrl).then(() => {{
                showCopied();
            }}).catch(() => {{
                const el = document.createElement('textarea');
                el.value = downloadUrl;
                document.body.appendChild(el);
                el.select();
                document.execCommand('copy');
                document.body.removeChild(el);
                showCopied();
            }});
        }}

        function showCopied() {{
            const btn = document.querySelector('.btn-copy');
            btn.textContent = '{btn_copied_text}';
            btn.classList.add('copied');
            setTimeout(() => {{
                btn.textContent = '{btn_copy_text}';
                btn.classList.remove('copied');
            }}, 2000);
        }}
    </script>

</body>
</html>"""
    return web.Response(text=html_content, content_type='text/html')


async def stream_handler(request):
    file_id = request.match_info.get("file_id")
    bot_client = request.app["bot_client"]

    try:
        msg, media = await _get_media(bot_client, file_id)
        if not media:
            return web.Response(text="❌ File not found", status=404)

        file_name, mime_type, file_size = _media_info(media)

        range_header = request.headers.get("Range")
        start = 0
        end = file_size - 1 if file_size else 0
        status = 200

        if range_header and file_size:
            try:
                range_val = range_header.strip().replace("bytes=", "")
                parts = range_val.split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
                if end >= file_size:
                    end = file_size - 1
                status = 206
            except Exception:
                start = 0
                end = file_size - 1
                status = 200

        encoded_name = quote(file_name)
        headers = {
            "Content-Type": mime_type if mime_type != "unknown" else "application/octet-stream",
            "Content-Disposition": f'inline; filename="{file_name}"; filename*=UTF-8\'\'{encoded_name}',
            "Accept-Ranges": "bytes",
            "Connection": "keep-alive"
        }

        if file_size:
            length = end - start + 1
            headers["Content-Length"] = str(length)
            if status == 206:
                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)

        async with _STREAM_SEMAPHORE:
            async for chunk in bot_client.stream_media(msg, offset=start, limit=end - start + 1 if status == 206 else None):
                await response.write(chunk)
                await response.drain()

        await response.write_eof()
        return response

    except (ConnectionResetError, asyncio.CancelledError):
        # Normal client disconnects (user paused or closed the player)
        pass
    except Exception as e:
        logger.error(f"Stream error: {e}")
        return web.Response(text=f"❌ Error: {e}", status=500)


async def download_handler(request):
    file_id = request.match_info.get("file_id")
    bot_client = request.app["bot_client"]

    try:
        msg, media = await _get_media(bot_client, file_id)
        if not media:
            return web.Response(text="❌ File not found", status=404)

        file_name, mime_type, file_size = _media_info(media)

        encoded_name = quote(file_name)
        headers = {
            "Content-Type": mime_type if mime_type != "unknown" else "application/octet-stream",
            "Content-Disposition": f'attachment; filename="{file_name}"; filename*=UTF-8\'\'{encoded_name}',
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        }

        response = web.StreamResponse(status=200, headers=headers)
        await response.prepare(request)

        async for chunk in bot_client.stream_media(msg):
            await response.write(chunk)
            await response.drain()

        await response.write_eof()
        return response

    except Exception as e:
        logger.error(f"Download error: {e}")
        return web.Response(text=f"❌ Error: {e}", status=500)
        
