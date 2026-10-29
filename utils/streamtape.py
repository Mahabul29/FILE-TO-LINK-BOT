"""
Streamtape integration.

* upload(): Streamtape downloads the file from this bot's /dl/<id> link (remote upload)
  so nothing is stored on the bot server.
* heal_loop(): every HEAL_INTERVAL_MIN minutes checks every file. If Streamtape deleted
  one, the bot uploads it again from the Telegram BIN_CHANNEL copy with the SAME NAME
  and swaps in the new Streamtape id.
* The bot's permanent link  https://<FQDN>/s/<file_id>  never changes - it always points
  to the current Streamtape file (see web/streamtape_redirect.py).
"""
import asyncio
import logging
import re
import time
from urllib.parse import quote

import aiohttp

from config import (
    FQDN, STREAMTAPE_LOGIN, STREAMTAPE_KEY, STREAMTAPE_FOLDER,
    HEAL_INTERVAL_MIN, UPLOAD_TIMEOUT_MIN, UPLOAD_PARALLEL,
)
from database import files_db
from database import streamtape_db as db

logger = logging.getLogger(__name__)

API = "https://api.streamtape.com"
enabled = bool(STREAMTAPE_LOGIN and STREAMTAPE_KEY)

_ID_RE = re.compile(r"(?:streamtape|strtape|stape)\.[a-z.]+/(?:v|e)/([A-Za-z0-9_-]+)", re.I)
_locks = {}
_upload_sem = asyncio.Semaphore(UPLOAD_PARALLEL)
MAX_FAILS = 5


def _base():
    return FQDN.replace("https://", "").replace("http://", "").strip().strip("/")


def dl_link(file_id):
    return f"https://{_base()}/dl/{file_id}"


def stable_link(file_id, embed=False):
    return f"https://{_base()}/{'se' if embed else 's'}/{file_id}"


def video_link(file_id, name=None):
    """Direct-video link for any video player / app. Never changes."""
    n = (name or "video.mp4").replace("/", "_")
    if "." not in n[-6:]:
        n += ".mp4"
    return f"https://{_base()}/sv/{file_id}/{quote(n)}"


def streamtape_url(st_id, name, embed=False):
    if embed:
        return f"https://streamtape.com/e/{st_id}"
    return f"https://streamtape.com/v/{st_id}/{quote(name or 'video.mp4')}"


def make_name(name, mime, file_id):
    """Name used on Streamtape. Keeps the original name; adds an extension if missing."""
    name = (name or "").strip()
    if not name:
        ext = ".mp4" if "video" in (mime or "") else ".bin"
        name = f"{file_id}{ext}"
    return name


async def _api(path, **params):
    params["login"] = STREAMTAPE_LOGIN
    params["key"] = STREAMTAPE_KEY
    params = {k: v for k, v in params.items() if v not in (None, "")}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(f"{API}{path}", params=params) as r:
            return await r.json(content_type=None)


def _parse_id(url):
    m = _ID_RE.search(str(url or ""))
    return m.group(1) if m else None


async def _find_by_name(name):
    """Fallback when the API says 'finished' but gives no file id: newest file with this name."""
    j = await _api("/file/listfolder", folder=STREAMTAPE_FOLDER)
    files = ((j.get("result") or {}).get("files")) or []
    same = [f for f in files if f.get("name") == name]
    if not same:
        return None
    same.sort(key=lambda f: f.get("created_at", 0), reverse=True)
    return same[0].get("linkid")


async def _remote_upload(file_id, name):
    """Returns the new Streamtape id, or None."""
    add = await _api("/remotedl/add", url=dl_link(file_id), name=name, folder=STREAMTAPE_FOLDER)
    if add.get("status") != 200 or not (add.get("result") or {}).get("id"):
        logger.warning(f"[streamtape] remotedl/add failed for {file_id}: {add.get('msg') or add.get('status')}")
        return None
    rid = add["result"]["id"]

    deadline = time.time() + UPLOAD_TIMEOUT_MIN * 60
    while time.time() < deadline:
        await asyncio.sleep(10)
        try:
            j = await _api("/remotedl/status", id=rid)
        except Exception as e:
            logger.warning(f"[streamtape] status check error: {e}")
            continue
        res = j.get("result") or {}
        row = res.get(rid) or (next(iter(res.values()), None) if isinstance(res, dict) else None)
        if not row:
            continue
        new_id = (str(row["extid"]) if row.get("extid") else None) or _parse_id(row.get("url"))
        if new_id:
            return new_id
        state = str(row.get("status", ""))
        if re.search(r"error|fail", state, re.I):
            logger.warning(f"[streamtape] remote upload failed for {file_id}: {state}")
            return None
        if re.search(r"finish|complet|done", state, re.I):
            return await _find_by_name(name)
    logger.warning(f"[streamtape] upload timed out for {file_id}")
    return None


async def upload(file_id, name, mime=None, healing=False):
    """Upload (or re-upload) one bot file. Returns the Streamtape id or None."""
    if not enabled:
        return None
    lock = _locks.setdefault(int(file_id), asyncio.Lock())
    if lock.locked():
        return None  # already uploading
    async with lock:
        rec = await db.get(file_id)
        # same name every time: the first name we stored always wins
        name = (rec or {}).get("name") or make_name(name, mime, file_id)
        page_link, player_link = stable_link(file_id), video_link(file_id, name)
        await db.upsert(file_id, name=name, status="uploading", page_link=page_link, player_link=player_link)
        try:
            await files_db.set_links(file_id, "streamtape", page_link, player_link)
        except Exception as e:
            logger.warning(f"[streamtape] could not store links on the file record: {e}")
        async with _upload_sem:
            try:
                new_id = await _remote_upload(file_id, name)
            except Exception as e:
                logger.error(f"[streamtape] upload error {file_id}: {e}")
                new_id = None
        if new_id:
            await db.upsert(file_id, st_id=new_id, status="ok", fails=0, last_check=time.time())
            if healing:
                await db.inc(file_id, healed=1)
            logger.info(f"[streamtape] {'restored' if healing else 'uploaded'} {file_id} -> {new_id} ({name})")
            return new_id
        await db.upsert(file_id, status="failed")
        await db.inc(file_id, fails=1)
        return None


async def file_status(ids):
    """{st_id: http-like status}. Missing ids are left out when the API call itself failed."""
    out = {}
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            j = await _api("/file/info", file=",".join(chunk))
        except Exception as e:
            logger.warning(f"[streamtape] info error: {e}")
            continue
        if j.get("status") == 200 and isinstance(j.get("result"), dict):
            for sid in chunk:
                out[sid] = (j["result"].get(sid) or {}).get("status", 404)
        elif j.get("status") == 404 and len(chunk) == 1:
            out[chunk[0]] = 404
        # 509 / 5xx / bad key: unknown, never treated as deleted
    return out


_direct_cache = {}   # st_id -> (url, expires_at)
_direct_locks = {}


def forget_direct(st_id):
    _direct_cache.pop(st_id, None)


async def direct_url(st_id, fresh=False):
    """Real video file URL from Streamtape (ticket -> wait -> link). Cached for 30 minutes."""
    if fresh:
        forget_direct(st_id)
    hit = _direct_cache.get(st_id)
    if hit and hit[1] > time.time():
        return hit[0]
    lock = _direct_locks.setdefault(st_id, asyncio.Lock())
    async with lock:
        hit = _direct_cache.get(st_id)
        if hit and hit[1] > time.time():
            return hit[0]
        try:
            t = await _api("/file/dlticket", file=st_id)
            if t.get("status") != 200 or not t.get("result"):
                logger.warning(f"[streamtape] dlticket failed for {st_id}: {t.get('msg') or t.get('status')}")
                return None
            ticket = t["result"]["ticket"]
            wait = int(t["result"].get("wait_time") or 0)
            if wait:
                await asyncio.sleep(min(wait, 20))
            d = await _api("/file/dl", file=st_id, ticket=ticket)
            if d.get("status") != 200 or not (d.get("result") or {}).get("url"):
                logger.warning(f"[streamtape] dl failed for {st_id}: {d.get('msg') or d.get('status')}")
                return None
            url = d["result"]["url"]
            _direct_cache[st_id] = (url, time.time() + 1800)
            return url
        except Exception as e:
            logger.error(f"[streamtape] direct url error {st_id}: {e}")
            return None


async def is_alive(file_id):
    """True / False, or None if unknown. Cached for 10 minutes in the DB row."""
    rec = await db.get(file_id)
    if not rec or not rec.get("st_id"):
        return None
    if time.time() - rec.get("last_check", 0) < 600:
        return rec.get("status") == "ok"
    st = await file_status([rec["st_id"]])
    code = st.get(rec["st_id"])
    if code is None:
        return None
    await db.upsert(file_id, last_check=time.time())
    return code == 200


async def heal_one(file_id):
    rec = await db.get(file_id)
    if not rec:
        return None
    return await upload(file_id, rec.get("name"), healing=True)


async def heal_loop():
    """Background task: finds deleted files and uploads them again."""
    await asyncio.sleep(30)
    while True:
        try:
            recs = await db.all_records()
            ok = [r for r in recs if r.get("status") == "ok" and r.get("st_id")]
            status = await file_status([r["st_id"] for r in ok])
            for r in ok:
                code = status.get(r["st_id"])
                if code is None:
                    continue
                if code == 200:
                    await db.upsert(r["file_id"], last_check=time.time())
                elif code == 404:
                    logger.info(f"[streamtape] {r['file_id']} ({r.get('name')}) was deleted - restoring")
                    await db.upsert(r["file_id"], status="failed", fails=0)
                    await heal_one(r["file_id"])
            # retry uploads that failed or got stuck (e.g. bot restarted mid-upload)
            for r in recs:
                stale = r.get("status") == "uploading" and time.time() - r.get("updated", 0) > UPLOAD_TIMEOUT_MIN * 60
                if (r.get("status") == "failed" or stale) and r.get("fails", 0) < MAX_FAILS:
                    await heal_one(r["file_id"])
        except Exception as e:
            logger.error(f"[streamtape] heal loop error: {e}")
        await asyncio.sleep(HEAL_INTERVAL_MIN * 60)

  
