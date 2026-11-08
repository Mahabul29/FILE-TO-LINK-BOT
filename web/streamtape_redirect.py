import asyncio
import aiohttp
from aiohttp import web
from config import STREAM_MODE
from database import streamtape_db as db
from utils import streamtape


async def _resolve(file_id):
    """
    Returns (record, state). state is 'ok' | 'restoring' | 'missing'.
    """
    rec = await db.get(file_id)
    if not rec:
        return None, "missing"
    if streamtape.enabled and rec.get("status") == "ok" and rec.get("st_id"):
        alive = await streamtape.is_alive(file_id)
        if alive is False:
            # Streamtape deleted it: restore in the background, same name, same bot link
            await db.upsert(file_id, status="failed", fails=0)
            asyncio.create_task(streamtape.heal_one(file_id))
            return rec, "restoring"
        return rec, "ok"
    return rec, "restoring"


async def stable_redirect(request):
    """
    /s/<file_id>  -> watch page, /se/<file_id> -> embed. The link never changes,
    it always points to the current Streamtape file.
    """
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
    # A video player / app pasted this link: give it the real video, not the host's HTML page
    if not embed and not _is_browser(request):
        return await stable_video(request)
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
        "video_link": streamtape.video_link(rec["file_id"], rec.get("name")),
    })


def _is_browser(request):
    """True for a normal web browser opening the link (wants an HTML page)."""
    accept = request.headers.get("Accept", "")
    ua = request.headers.get("User-Agent", "")
    return "text/html" in accept and "Mozilla" in ua and "ExoPlayer" not in ua and "VLC" not in ua


def _guess_type(name, upstream_type):
    ct = (upstream_type or "").lower()
    if ct.startswith(("video/", "audio/")) or "mpegurl" in ct:
        return upstream_type
    n = (name or "").lower()
    for ext, mt in ((".mkv", "video/x-matroska"), (".webm", "video/webm"), (".avi", "video/x-msvideo"),
                    (".mov", "video/quicktime"), (".mp3", "audio/mpeg"), (".m4a", "audio/mp4")):
        if n.endswith(ext):
            return mt
    return "video/mp4"


async def _open_upstream(session, st_id, range_header):
    """Opens Streamtape's video. Retries once with a fresh link."""
    for attempt in range(2):
        url = await streamtape.direct_url(st_id, fresh=attempt > 0)
        if not url:
            return None
        headers = {"Referer": "https://streamtape.com/", "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"}
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
        streamtape.forget_direct(st_id)
    return None


def _parse_range(header, size):
    """'bytes=a-b' / 'bytes=a-' / 'bytes=-n' -> (start, end), or None if unusable."""
    try:
        unit, _, spec = header.strip().partition("=")
        if unit.strip().lower() != "bytes" or "," in spec or size <= 0:
            return None
        a, _, b = spec.strip().partition("-")
        if a == "":
            n = int(b)
            return (max(0, size - n), size - 1) if n > 0 else None
        start = int(a)
        end = min(int(b) if b else size - 1, size - 1)
        return (start, end) if start <= end and start < size else None
    except Exception:
        return None


async def _proxy(request, st_id, name):
    """Streams the Streamtape file through the bot (supports seeking). Returns None if Streamtape fails.

    Seek fix: if Streamtape ignores the Range header and answers 200 (whole file), the player would
    restart the video from 0:00 on every skip. In that case the bot cuts the range itself and answers 206.
    """
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=60))
    try:
        range_header = request.headers.get("Range")
        up = await _open_upstream(session, st_id, range_header)
        if up is None:
            await session.close()
            return None
        out_headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": _guess_type(name, up.headers.get("Content-Type")),
            "Content-Disposition": f'inline; filename="{(name or "video.mp4").encode("ascii", "ignore").decode() or "video.mp4"}"',
            "Cache-Control": "no-store",
        }
        status = up.status
        skip = 0
        remaining = None  # bytes to send; None = send everything upstream gives
        if range_header and up.status == 200:
            try:
                total = int(up.headers.get("Content-Length") or 0)
            except ValueError:
                total = 0
            parsed = _parse_range(range_header, total)
            if parsed:
                start, end = parsed
                skip, remaining, status = start, end - start + 1, 206
                out_headers["Content-Range"] = f"bytes {start}-{end}/{total}"
                out_headers["Content-Length"] = str(remaining)
        if status == up.status:
            for h in ("Content-Length", "Content-Range"):
                if up.headers.get(h):
                    out_headers[h] = up.headers[h]
        resp = web.StreamResponse(status=status, headers=out_headers)
        await resp.prepare(request)
        if request.method != "HEAD":
            async for chunk in up.content.iter_chunked(256 * 1024):
                if skip:
                    if len(chunk) <= skip:
                        skip -= len(chunk)
                        continue
                    chunk = chunk[skip:]
                    skip = 0
                if remaining is not None:
                    chunk = chunk[:remaining]
                    remaining -= len(chunk)
                if chunk:
                    await resp.write(chunk)
                if remaining == 0:
                    break
        await resp.write_eof()
        up.release()
        return resp
    except (ConnectionResetError, asyncio.CancelledError):
        return web.Response(status=499)
    finally:
        await session.close()


async def stable_video(request):
    """
    /sv/<file_id>[/<name>.mp4]  -> the real video file, playable in any video player / app.
    The link never changes. Order: Streamtape -> Telegram copy (/stream/<id>),
    so playback never breaks while Streamtape is down or a file is being restored.
    """
    file_id = request.match_info["file_id"]
    rec, state = await _resolve(file_id)
    if state == "missing":
        return web.Response(text="❌ File not found", status=404)

    if state == "ok":
        st_id = rec["st_id"]
        # Direct links are locked to the IP that asked for them (this server), so the bot
        # streams the bytes itself; a redirect only works with STREAM_MODE=redirect.
        if STREAM_MODE == "redirect" and _is_browser(request):
            url = await streamtape.direct_url(st_id)
            if url:
                raise web.HTTPFound(url)
        resp = await _proxy(request, st_id, rec.get("name"))
        if resp is not None:
            return resp

    # restoring / Streamtape has a problem -> play from the Telegram copy
    raise web.HTTPFound(f"/stream/{file_id}")
