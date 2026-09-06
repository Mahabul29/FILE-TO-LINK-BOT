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
            icon = "🎬"
            file_type = "Video"
            player_tag = f'''
            <video controls autoplay playsinline preload="metadata">
                <source src="/stream/{file_id}" type="{mime_type}">
                Your browser does not support this video.
            </video>
            '''
            playable_note = ""
        elif "audio" in mime_type:
            icon = "🎵"
            file_type = "Audio"
            player_tag = f'''
            <audio controls autoplay preload="metadata">
                <source src="/stream/{file_id}" type="{mime_type}">
                Your browser does not support this audio.
            </audio>
            '''
            playable_note = ""
        else:
            icon = "📁"
            file_type = "Document"
            player_tag = ""
            playable_note = "<p class='warn'>⚠️ This file may not play in browser. You can download it below.</p>"

    except Exception as e:
        logger.error(f"File info error: {e}")
        file_name = "Unknown"
        mime_type = "unknown"
        size_mb = 0
        icon = "📁"
        file_type = "File"
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
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0b1521;
            color: white;
            font-family: 'Segoe UI', sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px 15px 40px;
            min-height: 100vh;
        }}
        .title {{
            color: #2481cc;
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
            text-align: center;
            line-height: 1.4;
            word-break: break-word;
            max-width: 850px;
            width: 100%;
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

    <div class="title">{icon} {file_name}</div>

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
            <span class="info-value">{file_type} ({mime_type})</span>
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

        if file_size:
            async for chunk in _chunked_stream(bot_client, msg, start, end):
                if chunk:
                    await response.write(chunk)
        else:
            # No known file_size — fall back to plain sequential stream
            async for chunk in bot_client.stream_media(msg):
                await response.write(chunk)

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
