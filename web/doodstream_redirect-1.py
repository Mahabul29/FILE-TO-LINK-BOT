import asyncio
import aiohttp
from aiohttp import web
from config import STREAM_MODE
from database import doodstream_db as db
from utils import doodstream
from web.streamtape_redirect import _is_browser, _guess_type


async def _resolve(file_id):
    """Returns (record, state) where state is 'ok' | 'restoring' | 'missing'."""
    rec = await db.get(file_id)
    if not rec:
        return None, "missing"
    if rec.get("status") == "ok" and rec.get("st_id"):
        alive = await doodstream.is_alive(file_id)
        if alive is False:
            await db.upsert(file_id, status="failed", fails=0)
            asyncio.create_task(doodstream.heal_one(file_id))
            return rec, "restoring"
        return rec, "ok"
    return rec, "restoring"


async def dood_redirect(request):
    """/d/<file_id> -> DoodStream page, /de/<file_id> -> embed. Apps/players get the real video."""
    file_id = request.match_info["file_id"]
    embed = request.path.startswith("/de/")
    rec, state = await _resolve(file_id)
    if state == "missing":
        return web.Response(text="❌ File not found", status=404)
    if state == "restoring":
        return web.Response(text="⏳ This file is being restored. Try again in a minute.",
                            status=503, headers={"Retry-After": "60"})
    if not embed and not _is_browser(request):
        return await dood_video(request)
    raise web.HTTPFound(doodstream.dood_url(rec["st_id"], embed))


async def dood_info(request):
    """/dinfo/<file_id> -> JSON with the current DoodStream code/links."""
    file_id = request.match_info["file_id"]
    rec = await db.get(file_id)
    if not rec:
        return web.json_response({"error": "not found"}, status=404)
    code = rec.get("st_id")
    return web.json_response({
        "file_id": rec["file_id"],
        "name": rec.get("name"),
        "status": rec.get("status"),
        "healed": rec.get("healed", 0),
        "doodstream_id": code,
        "watch": doodstream.dood_url(code) if code else None,
        "embed": doodstream.dood_url(code, True) if code else None,
        "stable_link": doodstream.stable_link(rec["file_id"]),
        "video_link": doodstream.video_link(rec["file_id"], rec.get("name")),
    })


async def _open_upstream(session, code, range_header):
    for attempt in range(2):
        url = await doodstream.direct_url(code, fresh=attempt > 0)
        if not url:
            return None
        headers = {"Referer": doodstream.direct_referer(code), "User-Agent": doodstream.UA}
        if range_header:
            headers["Range"] = range_header
        try:
            up = await session.get(url, headers=headers, allow_redirects=True)
        except Exception:
            continue
        ct = (up.headers.get("Content-Type") or "").lower()
        if up.status in (200, 206) and "text/html" not in ct:
            return up
        up.release()
        doodstream.forget_direct(code)
    return None


async def _proxy(request, code, name):
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=60))
    try:
        up = await _open_upstream(session, code, request.headers.get("Range"))
        if up is None:
            await session.close()
            return None
        out_headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": _guess_type(name, up.headers.get("Content-Type")),
            "Content-Disposition": f'inline; filename="{(name or "video.mp4").encode("ascii", "ignore").decode() or "video.mp4"}"',
            "Cache-Control": "no-store",
        }
        for h in ("Content-Length", "Content-Range"):
            if up.headers.get(h):
                out_headers[h] = up.headers[h]
        resp = web.StreamResponse(status=up.status, headers=out_headers)
        await resp.prepare(request)
        if request.method != "HEAD":
            async for chunk in up.content.iter_chunked(256 * 1024):
                await resp.write(chunk)
        await resp.write_eof()
        up.release()
        return resp
    except (ConnectionResetError, asyncio.CancelledError):
        return web.Response(status=499)
    finally:
        await session.close()


async def dood_video(request):
    """
    /dv/<file_id>[/<name>.mp4] -> the real video file for any video player / app.
    Falls back to the Telegram copy (/stream/<id>) if DoodStream is down or restoring.
    """
    file_id = request.match_info["file_id"]
    rec, state = await _resolve(file_id)
    if state == "missing":
        return web.Response(text="❌ File not found", status=404)
    if state == "ok":
        if STREAM_MODE == "redirect":
            url = await doodstream.direct_url(rec["st_id"])
            if url:
                raise web.HTTPFound(url)
        else:
            resp = await _proxy(request, rec["st_id"], rec.get("name"))
            if resp is not None:
                return resp
    raise web.HTTPFound(f"/stream/{file_id}")
    
