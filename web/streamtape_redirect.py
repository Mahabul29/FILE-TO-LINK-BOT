import asyncio
from aiohttp import web
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
    })
