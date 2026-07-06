import logging
from aiohttp import web
from config import BIN_CHANNEL, FQDN

logger = logging.getLogger(__name__)


def _media_info(media):
    file_name = getattr(media, "file_name", "Unknown File")
    mime_type = getattr(media, "mime_type", "application/octet-stream") or "application/octet-stream"
    file_size = getattr(media, "file_size", 0) or 0
    return file_name, mime_type, file_size


def _format_size(size_bytes):
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


async def video_play(request):
    file_id = request.match_info.get("file_id")
    bot_client = request.app["bot_client"]

    try:
        msg = await bot_client.get_messages(int(BIN_CHANNEL), int(file_id))
        media = msg.document or msg.video or msg.audio or msg.photo
        if not media:
            return web.Response(text="❌ File not found", status=404)

        file_name, mime_type, file_size = _media_info(media)
        size_fmt = _format_size(file_size)

        if "video" in mime_type:
            icon = "🎬"
            file_type = "Video"
            player_tag = f'''
            <div class="player-wrap">
                <video id="player" playsinline preload="metadata" data-plyr>
                    <source src="/stream/{file_id}" type="{mime_type}">
                    Your browser does not support this video.
                </video>
            </div>
            '''
            note = ""
        elif "audio" in mime_type:
            icon = "🎵"
            file_type = "Audio"
            player_tag = f'''
            <div class="player-wrap audio-wrap">
                <audio id="player" controls autoplay preload="metadata">
                    <source src="/stream/{file_id}" type="{mime_type}">
                    Your browser does not support this audio.
                </audio>
            </div>
            '''
            note = ""
        else:
            icon = "📁"
            file_type = "File"
            player_tag = ""
            note = "<p class='warn'>⚠️ This file type cannot be previewed in browser. Please download it.</p>"

    except Exception as e:
        logger.error(f"video_play error: {e}")
        file_name = "Unknown"
        mime_type = "unknown"
        file_size = 0
        size_fmt = "—"
        icon = "📁"
        file_type = "File"
        player_tag = ""
        note = "<p class='warn'>⚠️ Could not fetch file info.</p>"

    clean_fqdn = FQDN.replace("https://", "").replace("http://", "").rstrip("/")
    download_url = f"https://{clean_fqdn}/dl/{file_id}"
    stream_url = f"https://{clean_fqdn}/stream/{file_id}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{file_name}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css">
    <style>
        *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}

        :root {{
            --bg: #080c12;
            --surface: #0e1720;
            --border: rgba(36, 129, 204, 0.18);
            --accent: #2481cc;
            --accent-dim: rgba(36, 129, 204, 0.12);
            --accent-hover: #1a6aaa;
            --green: #1db954;
            --green-hover: #17a349;
            --text: #e8f0f8;
            --muted: #5a7a94;
            --warn-bg: #1a1000;
            --warn-border: rgba(243, 156, 18, 0.4);
            --warn-text: #f39c12;
        }}

        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'DM Mono', monospace;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 28px 16px 60px;
            background-image:
                radial-gradient(ellipse 60% 40% at 50% 0%, rgba(36,129,204,0.07) 0%, transparent 70%);
        }}

        .header {{
            width: 100%;
            max-width: 860px;
            display: flex;
            align-items: flex-start;
            gap: 14px;
            margin-bottom: 20px;
        }}
        .icon-badge {{
            width: 44px;
            height: 44px;
            min-width: 44px;
            background: var(--accent-dim);
            border: 1px solid var(--border);
            border-radius: 10px;
            display: grid;
            place-items: center;
            font-size: 20px;
            line-height: 1;
        }}
        .title-group {{
            display: flex;
            flex-direction: column;
            gap: 4px;
            min-width: 0;
        }}
        .file-title {{
            font-family: 'Syne', sans-serif;
            font-size: 17px;
            font-weight: 700;
            color: var(--text);
            word-break: break-word;
            line-height: 1.3;
        }}
        .file-subtitle {{
            font-size: 11px;
            color: var(--muted);
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }}

        .info-box {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            width: 100%;
            max-width: 860px;
            margin-bottom: 16px;
            overflow: hidden;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            padding: 11px 16px;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            font-size: 12px;
        }}
        .info-row:last-child {{ border-bottom: none; }}
        .info-label {{
            color: var(--muted);
            display: flex;
            align-items: center;
            gap: 6px;
            white-space: nowrap;
        }}
        .info-value {{
            color: var(--text);
            font-weight: 500;
            text-align: right;
            word-break: break-all;
        }}

        .player-wrap {{
            width: 100%;
            max-width: 860px;
            border-radius: 12px;
            overflow: hidden;
            background: #000;
            margin-bottom: 16px;
            border: 1px solid var(--border);
        }}
        .player-wrap video,
        .player-wrap audio {{
            width: 100%;
            display: block;
            outline: none;
            border: none;
        }}
        .audio-wrap {{
            background: var(--surface);
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .audio-wrap audio {{
            width: 100%;
        }}

        .plyr {{ --plyr-color-main: var(--accent); border-radius: 12px; }}
        .plyr__control--overlaid {{ background: rgba(36,129,204,0.85); }}
        .plyr__control--overlaid:hover {{ background: var(--accent); }}
        .plyr__controls {{ background: linear-gradient(transparent, rgba(0,0,0,0.75)); }}
        .plyr__menu__container {{ background: rgba(8,12,18,0.97); backdrop-filter: blur(6px); }}
        .plyr__control.plyr__tab-focus,
        .plyr__control:hover {{ background: var(--accent); }}

        .warn {{
            color: var(--warn-text);
            background: var(--warn-bg);
            border: 1px solid var(--warn-border);
            border-radius: 10px;
            padding: 11px 16px;
            margin-bottom: 14px;
            font-size: 12px;
            width: 100%;
            max-width: 860px;
            text-align: center;
        }}

        .btn-row {{
            display: flex;
            gap: 10px;
            width: 100%;
            max-width: 860px;
        }}
        .btn {{
            flex: 1;
            padding: 14px 12px;
            color: #fff;
            text-decoration: none;
            border-radius: 11px;
            font-family: 'Syne', sans-serif;
            font-weight: 700;
            font-size: 13px;
            text-align: center;
            border: none;
            cursor: pointer;
            transition: background 0.15s, transform 0.1s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            letter-spacing: 0.01em;
        }}
        .btn:active {{ transform: scale(0.97); }}
        .btn-download {{
            background: var(--green);
        }}
        .btn-download:hover {{ background: var(--green-hover); }}
        .btn-copy {{
            background: var(--accent);
        }}
        .btn-copy:hover {{ background: var(--accent-hover); }}
        .btn-copy.copied {{
            background: #155fa0;
        }}

        .divider {{
            width: 100%;
            max-width: 860px;
            height: 1px;
            background: var(--border);
            margin: 18px 0;
        }}

        @media (max-width: 480px) {{
            .file-title {{ font-size: 15px; }}
            .btn {{ font-size: 12px; padding: 13px 8px; }}
        }}
    </style>
</head>
<body>

    <div class="header">
        <div class="icon-badge">{icon}</div>
        <div class="title-group">
            <div class="file-title">{file_name}</div>
            <div class="file-subtitle">{file_type} &nbsp;·&nbsp; {size_fmt}</div>
        </div>
    </div>

    <div class="info-box">
        <div class="info-row">
            <span class="info-label">📄 File Name</span>
            <span class="info-value">{file_name}</span>
        </div>
        <div class="info-row">
            <span class="info-label">📦 Size</span>
            <span class="info-value">{size_fmt}</span>
        </div>
        <div class="info-row">
            <span class="info-label">🎞️ Type</span>
            <span class="info-value">{file_type} &nbsp;<span style="color:var(--muted)">({mime_type})</span></span>
        </div>
        <div class="info-row">
            <span class="info-label">🆔 File ID</span>
            <span class="info-value">{file_id}</span>
        </div>
    </div>

    {note}
    {player_tag}

    <div class="btn-row">
        <a href="{download_url}" class="btn btn-download">⬇ Download</a>
        <button class="btn btn-copy" onclick="copyLink()">🔗 Copy Link</button>
    </div>

    <script src="https://cdn.plyr.io/3.7.8/plyr.polyfilled.js"></script>
    <script>
        function copyLink() {{
            const url = "{download_url}";
            navigator.clipboard.writeText(url).then(() => {{
                const btn = document.querySelector('.btn-copy');
                const orig = btn.innerHTML;
                btn.innerHTML = '✅ Copied!';
                btn.classList.add('copied');
                setTimeout(() => {{
                    btn.innerHTML = orig;
                    btn.classList.remove('copied');
                }}, 2000);
            }});
        }}

        const playerEl = document.querySelector('[data-plyr]');
        if (playerEl) {{
            new Plyr(playerEl, {{
                seekTime: 10,
                autoplay: true,
                settings: ['captions', 'speed', 'loop'],
                speed: {{ selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] }},
                controls: [
                    'play-large', 'rewind', 'play', 'fast-forward',
                    'progress', 'current-time', 'duration',
                    'mute', 'captions', 'settings',
                    'pip', 'fullscreen'
                ]
            }});
        }}
    </script>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


async def stream_handler(request):
    """Streams file with proper Range request support for seeking."""
    file_id = request.match_info.get("file_id")
    bot_client = request.app["bot_client"]

    try:
        msg = await bot_client.get_messages(int(BIN_CHANNEL), int(file_id))
        media = msg.document or msg.video or msg.audio or msg.photo
        if not media:
            return web.Response(text="❌ File not found", status=404)

        file_name, mime_type, file_size = _media_info(media)
        content_type = mime_type if mime_type != "unknown" else "application/octet-stream"

        range_header = request.headers.get("Range")
        start = 0
        end = file_size - 1 if file_size else None

        if range_header and file_size:
            try:
                range_val = range_header.strip().replace("bytes=", "")
                parts = range_val.split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else file_size - 1
                end = min(end, file_size - 1)
            except Exception:
                return web.Response(text="❌ Invalid Range header", status=416)

        is_partial = range_header and file_size
        status = 206 if is_partial else 200

        headers = {
            "Content-Type": content_type,
            "Content-Disposition": f'inline; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        }

        if file_size:
            if is_partial:
                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
                headers["Content-Length"] = str(end - start + 1)
            else:
                headers["Content-Length"] = str(file_size)

        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)

        async for chunk in bot_client.stream_media(msg, offset=start // (1024 * 1024)):
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
        msg = await bot_client.get_messages(int(BIN_CHANNEL), int(file_id))
        media = msg.document or msg.video or msg.audio or msg.photo
        if not media:
            return web.Response(text="❌ File not found", status=404)

        file_name, mime_type, file_size = _media_info(media)
        content_type = mime_type if mime_type != "unknown" else "application/octet-stream"

        headers = {
            "Content-Type": content_type,
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        }
        if file_size:
            headers["Content-Length"] = str(file_size)

        response = web.StreamResponse(status=200, headers=headers)
        await response.prepare(request)

        async for chunk in bot_client.stream_media(msg):
            await response.write(chunk)

        await response.write_eof()
        return response

    except Exception as e:
        logger.error(f"Download error: {e}")
        return web.Response(text=f"❌ Error: {e}", status=500)
