import asyncio
import logging
import math
from aiohttp import web
from config import BIN_CHANNEL, FQDN

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # Pyrogram's internal download chunk size (1MB)


def _media_info(media):
    file_name = getattr(media, "file_name", "Unknown File")
    mime_type = getattr(media, "mime_type", "application/octet-stream") or "application/octet-stream"
    file_size = getattr(media, "file_size", 0) or 0
    return file_name, mime_type, file_size


_ICON_VIDEO = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 4 20 12 6 20 6 4"></polygon></svg>'
_ICON_AUDIO = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>'
_ICON_DOC = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>'


def _type_badge(mime_type):
    # (label, accent color, svg icon) — same accent system as the home page
    if "video" in mime_type:
        return "Video", "#ef6461", _ICON_VIDEO
    if "audio" in mime_type:
        return "Audio", "#3ddc97", _ICON_AUDIO
    return "Document", "#5a7a94", _ICON_DOC


async def _get_media(bot_client, file_id):
    msg = await bot_client.get_messages(int(BIN_CHANNEL), int(file_id))
    media = msg.document or msg.video or msg.audio or msg.photo
    return msg, media


async def _chunked_stream(bot_client, msg, start: int, end: int):
    """
    Yield exactly the bytes in [start, end] (inclusive) from Telegram,
    aligned to Pyrogram's internal 1MB chunk boundaries.
    """
    offset = start - (start % CHUNK_SIZE)
    first_cut = start - offset
    last_cut = (end % CHUNK_SIZE) + 1
    part_count = math.ceil(end / CHUNK_SIZE) - math.floor(offset / CHUNK_SIZE)

    current = 0
    async for chunk in bot_client.stream_media(
        msg, offset=offset // CHUNK_SIZE, limit=part_count
    ):
        if part_count == 1:
            yield chunk[first_cut:last_cut]
        elif current == 0:
            yield chunk[first_cut:]
        elif current == part_count - 1:
            yield chunk[:last_cut]
        else:
            yield chunk
        current += 1


async def video_play(request):
    file_id = request.match_info.get("file_id")
    bot_client = request.app["bot_client"]

    try:
        msg, media = await _get_media(bot_client, file_id)
        if not media:
            return web.Response(text="❌ File not found", status=404)

        file_name, mime_type, file_size = _media_info(media)
        size_mb = round(file_size / (1024 * 1024), 2)

        if "video" in mime_type:
            file_type, accent, icon_svg = _type_badge(mime_type)
            player_tag = f'''
            <video controls autoplay playsinline preload="metadata">
                <source src="/stream/{file_id}" type="{mime_type}">
                Your browser does not support this video.
            </video>
            '''
            playable_note = ""
        elif "audio" in mime_type:
            file_type, accent, icon_svg = _type_badge(mime_type)
            player_tag = f'''
            <audio controls autoplay preload="metadata">
                <source src="/stream/{file_id}" type="{mime_type}">
                Your browser does not support this audio.
            </audio>
            '''
            playable_note = ""
        else:
            file_type, accent, icon_svg = _type_badge(mime_type)
            player_tag = ""
            playable_note = "<p class='warn'>⚠️ This file may not play in browser. You can download it below.</p>"

    except Exception as e:
        logger.error(f"File info error: {e}")
        file_name = "Unknown"
        mime_type = "unknown"
        size_mb = 0
        file_type, accent, icon_svg = "File", "#5a7a94", _ICON_DOC
        player_tag = ""
        playable_note = "<p class='warn'>⚠️ Could not fetch file info.</p>"
        file_id = request.match_info.get("file_id")

    clean_fqdn = FQDN.replace("https://", "").replace("http://", "").rstrip("/")
    download_url = f"https://{clean_fqdn}/dl/{file_id}"

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
    </style>
</head>
<body>

    <div class="title-row">
        <span class="badge">{icon_svg}</span>
        <span class="title-text">{file_name}</span>
    </div>

    {playable_note}
    {player_tag}

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
        <a href="{download_url}" class="btn btn-download">⬇ Download</a>
        <button class="btn btn-copy" onclick="copyLink()">🔗 Copy Link</button>
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
            btn.textContent = '✅ Copied!';
            btn.classList.add('copied');
            setTimeout(() => {{
                btn.textContent = '🔗 Copy Link';
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

        headers = {
            "Content-Type": mime_type if mime_type != "unknown" else "application/octet-stream",
            "Content-Disposition": f'inline; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        }

        if file_size:
            length = end - start + 1
            headers["Content-Length"] = str(length)
            if status == 206:
                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)

        CHUNK_TIMEOUT = 20  # seconds — if Telegram/network stalls this long, give up and close

        try:
            if file_size:
                gen = _chunked_stream(bot_client, msg, start, end)
            else:
                gen = bot_client.stream_media(msg)

            while True:
                try:
                    chunk = await asyncio.wait_for(gen.__anext__(), timeout=CHUNK_TIMEOUT)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.warning(f"Stream stalled (no data for {CHUNK_TIMEOUT}s) on {file_id}, closing")
                    break
                if chunk:
                    await response.write(chunk)
        except (ConnectionResetError, asyncio.CancelledError):
            # Client dropped connection (e.g. lost internet) — nothing more to do.
            pass

        await response.write_eof()
        return response

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

        headers = {
            "Content-Type": mime_type if mime_type != "unknown" else "application/octet-stream",
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        }

        response = web.StreamResponse(status=200, headers=headers)
        await response.prepare(request)

        async for chunk in bot_client.stream_media(msg):
            await response.write(chunk)

        await response.write_eof()
        return response

    except Exception as e:
        logger.error(f"Download error: {e}")
        return web.Response(text=f"❌ Error: {e}", status=500)
            
