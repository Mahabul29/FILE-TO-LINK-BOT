import asyncio
import aiohttp
from aiohttp import web
from config import STREAM_MODE
from database import streamtape_db as db
from utils import streamtape


async def _resolve(file_id):
    """Returns (record, state) where state is 'ok' | 'restoring' | 'missing'."""
    rec = await db.get(file_id)
    if not rec:
        return None, "missing"
    if rec.get("status") == "ok" and rec.get("st_id"):
        alive = await streamtape.is_alive(file_id)
        if alive is False:
            # Streamtape deleted it: restore in the background, same name, same bot link
            await db.upsert(file_id, status="failed", fails=0)
            asyncio.create_task(streamtape.heal_one(file_id))
            return rec, "restoring"
        return rec, "ok"
    return rec, "restoring"


async def stable_redirect(request):
    """/s/<file_id> -> Streamtape page, /se/<file_id> -> Streamtape embed. The bot link never changes."""
    file_id = request.match_info["file_id"]
    embed = request.path.startswith("/se/")
    rec, state = await _resolve(file_id)
    if state == "missing":
        return web.Response(text="❌ File not found", status=404)
    if state == "restoring":
        return web.Response(
            text="⏳ This file is being restored. Try again in a minute.",
            status=503, headers={"Retry-After": "60"},
        )
    raise web.HTTPFound(streamtape.streamtape_url(rec["st_id"], rec.get("name"), embed))


async def stable_info(request):
    """/sinfo/<file_id> -> JSON with the current Streamtape id/links (for your apps)."""
    file_id = request.match_info["file_id"]
    rec = await db.get(file_id)
    if not rec:
        return web.json_response({"error": "not found"}, status=404)
    st_id = rec.get("st_id")
    return web.json_response({
        "file_id": rec["file_id"],
        "name": rec.get("name"),
        "status": rec.get("status"),
        "healed": rec.get("healed", 0),
        "streamtape_id": st_id,
        "watch": streamtape.streamtape_url(st_id, rec.get("name")) if st_id else None,
        "embed": streamtape.streamtape_url(st_id, rec.get("name"), True) if st_id else None,
        "stable_link": streamtape.stable_link(rec["file_id"]),
        "video_link": streamtape.video_link(rec["file_id"]),
    })


async def _proxy(request, url):
    """Streams the Streamtape file through the bot (supports seeking)."""
    headers = {}
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_read=60))
    try:
        up = await session.get(url, headers=headers)
        out_headers = {"Accept-Ranges": "bytes"}
        for h in ("Content-Type", "Content-Length", "Content-Range"):
            if up.headers.get(h):
                out_headers[h] = up.headers[h]
        resp = web.StreamResponse(status=up.status, headers=out_headers)
        await resp.prepare(request)
        async for chunk in up.content.iter_chunked(256 * 1024):
            await resp.write(chunk)
        await resp.write_eof()
        return resp
    except (ConnectionResetError, asyncio.CancelledError):
        return web.Response(status=499)
    finally:
        await session.close()


async def stable_video(request):
    """
    /sv/<file_id>  -> the real video file, for apps like CastFlix (ExoPlayer).
    The link never changes. If Streamtape has a problem or the file is being restored,
    the video plays from the Telegram copy (/stream/<id>) so playback never breaks.
    """
    file_id = request.match_info["file_id"]
    rec, state = await _resolve(file_id)
    if state == "missing":
        return web.Response(text="❌ File not found", status=404)

    if state == "ok":
        url = await streamtape.direct_url(rec["st_id"])
        if url:
            if STREAM_MODE == "proxy":
                return await _proxy(request, url)
            raise web.HTTPFound(url)

    # restoring / Streamtape problem -> play from the Telegram copy
    raise web.HTTPFound(f"/stream/{file_id}")
    
