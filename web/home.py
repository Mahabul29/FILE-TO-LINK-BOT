import logging
from aiohttp import web
from datetime import datetime
from database.files_db import get_all_files, total_files_count

logger = logging.getLogger(__name__)


def _format_size(size_bytes):
    if not size_bytes:
        return "—"
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


def _icon_for(mime_type):
    if "video" in mime_type:
        return "🎬"
    if "audio" in mime_type:
        return "🎵"
    if "image" in mime_type:
        return "🖼️"
    return "📁"


async def home_page(request):
    try:
        files = await get_all_files(limit=300)
        total = await total_files_count()
    except Exception as e:
        logger.error(f"home_page db error: {e}")
        files = []
        total = 0

    cards = ""
    if not files:
        cards = "<div class='empty'>📭 No files uploaded yet.</div>"
    else:
        for f in files:
            file_id = f.get("file_id")
            name = f.get("file_name", "Unknown")
            size = _format_size(f.get("file_size", 0))
            mime_type = f.get("mime_type", "") or ""
            icon = _icon_for(mime_type)
            ts = f.get("upload_date")
            date_str = datetime.fromtimestamp(ts).strftime("%d %b %Y") if ts else "—"

            cards += f"""
            <a class="card" href="/watch/{file_id}">
                <div class="card-icon">{icon}</div>
                <div class="card-body">
                    <div class="card-name">{name}</div>
                    <div class="card-meta">{size} &nbsp;·&nbsp; {date_str}</div>
                </div>
                <div class="card-arrow">›</div>
            </a>
            """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>All Files</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
        :root {{
            --bg: #080c12;
            --surface: #0e1720;
            --border: rgba(36, 129, 204, 0.18);
            --accent: #2481cc;
            --accent-dim: rgba(36, 129, 204, 0.12);
            --text: #e8f0f8;
            --muted: #5a7a94;
        }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'DM Mono', monospace;
            min-height: 100vh;
            padding: 28px 16px 60px;
            background-image: radial-gradient(ellipse 60% 40% at 50% 0%, rgba(36,129,204,0.07) 0%, transparent 70%);
        }}
        .wrap {{ max-width: 860px; margin: 0 auto; }}
        .header {{ margin-bottom: 22px; }}
        .header h1 {{
            font-family: 'Syne', sans-serif;
            font-size: 22px;
            font-weight: 800;
            margin-bottom: 4px;
        }}
        .header p {{ color: var(--muted); font-size: 12px; }}
        .card {{
            display: flex;
            align-items: center;
            gap: 14px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px 16px;
            margin-bottom: 10px;
            text-decoration: none;
            color: var(--text);
            transition: background 0.15s, transform 0.1s;
        }}
        .card:active {{ transform: scale(0.98); }}
        .card:hover {{ background: #101c28; }}
        .card-icon {{
            width: 40px; height: 40px; min-width: 40px;
            background: var(--accent-dim);
            border-radius: 9px;
            display: grid; place-items: center;
            font-size: 18px;
        }}
        .card-body {{ flex: 1; min-width: 0; }}
        .card-name {{
            font-size: 13px; font-weight: 500;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .card-meta {{ font-size: 11px; color: var(--muted); margin-top: 3px; }}
        .card-arrow {{ color: var(--muted); font-size: 20px; }}
        .empty {{
            text-align: center; color: var(--muted);
            padding: 60px 20px; font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="header">
            <h1>📂 All Files</h1>
            <p>{total} file(s) uploaded</p>
        </div>
        {cards}
    </div>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")
