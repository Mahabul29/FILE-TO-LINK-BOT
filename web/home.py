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


def _type_meta(mime_type):
    # (short tag, accent color) — color carries the file type instead of an icon box
    if "video" in mime_type:
        return "VID", "#ef6461"
    if "audio" in mime_type:
        return "AUD", "#3ddc97"
    if "image" in mime_type:
        return "IMG", "#e8b34c"
    return "DOC", "#5a7a94"


async def home_page(request):
    try:
        files = await get_all_files(limit=300)
        total = await total_files_count()
    except Exception as e:
        logger.error(f"home_page db error: {e}")
        files = []
        total = 0

    rows = ""
    if not files:
        rows = """
        <div class="empty">
            <div class="empty-title">Nothing indexed yet</div>
            <div class="empty-sub">Files sent to the bot will show up here.</div>
        </div>
        """
    else:
        for f in files:
            file_id = f.get("file_id")
            name = f.get("file_name", "Unknown")
            size = _format_size(f.get("file_size", 0))
            mime_type = f.get("mime_type", "") or ""
            tag, color = _type_meta(mime_type)
            ts = f.get("upload_date")
            date_str = datetime.fromtimestamp(ts).strftime("%d %b") if ts else "—"

            rows += f"""
            <a class="row" href="/watch/{file_id}" style="--accent:{color}">
                <span class="row-bar"></span>
                <span class="row-tag">{tag}</span>
                <span class="row-name">{name}</span>
                <span class="row-size">{size}</span>
                <span class="row-date">{date_str}</span>
            </a>
            """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Index</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
        :root {{
            --bg: #080c12;
            --surface: #0e1720;
            --border: rgba(36, 129, 204, 0.16);
            --accent: #2481cc;
            --text: #e8f0f8;
            --muted: #5a7a94;
        }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'DM Mono', monospace;
            min-height: 100vh;
            padding: 28px 16px 60px;
        }}
        .wrap {{ max-width: 860px; margin: 0 auto; }}
        .header {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 4px;
        }}
        .header h1 {{
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            font-size: 22px;
            letter-spacing: -0.01em;
        }}
        .header .count {{
            font-size: 12px;
            color: var(--muted);
        }}
        .col-heads {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 4px 8px;
            font-size: 10px;
            color: var(--muted);
        }}
        .col-heads .ch-tag {{ width: 34px; }}
        .col-heads .ch-name {{ flex: 1; }}
        .col-heads .ch-size {{ width: 64px; text-align: right; }}
        .col-heads .ch-date {{ width: 44px; text-align: right; }}
        .row {{
            position: relative;
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 4px 12px 14px;
            text-decoration: none;
            color: var(--text);
            border-bottom: 1px solid var(--border);
        }}
        .row:active {{ background: var(--surface); }}
        .row-bar {{
            position: absolute;
            left: 0; top: 8px; bottom: 8px;
            width: 3px;
            border-radius: 2px;
            background: var(--accent);
        }}
        .row-tag {{
            width: 34px;
            font-size: 10px;
            font-weight: 500;
            color: var(--accent);
            letter-spacing: 0.02em;
        }}
        .row-name {{
            flex: 1;
            min-width: 0;
            font-size: 13px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .row-size {{
            width: 64px;
            text-align: right;
            font-size: 11px;
            color: var(--muted);
        }}
        .row-date {{
            width: 44px;
            text-align: right;
            font-size: 11px;
            color: var(--muted);
        }}
        .empty {{
            padding: 70px 10px;
            text-align: center;
        }}
        .empty-title {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 6px;
        }}
        .empty-sub {{
            font-size: 12px;
            color: var(--muted);
        }}
        @media (max-width: 420px) {{
            .row-date {{ display: none; }}
            .col-heads .ch-date {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="header">
            <h1>Index</h1>
            <span class="count">{total} file{'s' if total != 1 else ''}</span>
        </div>
        <div class="col-heads">
            <span class="ch-tag">TYPE</span>
            <span class="ch-name">NAME</span>
            <span class="ch-size">SIZE</span>
            <span class="ch-date">DATE</span>
        </div>
        {rows}
    </div>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")
    
