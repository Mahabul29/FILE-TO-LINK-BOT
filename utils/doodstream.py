"""
DoodStream integration (same idea as utils/streamtape.py).

* upload(): DoodStream downloads the file from this bot's /dl/<id> link (remote upload)
  so nothing is stored on the bot server.
* heal_loop(): every HEAL_INTERVAL_MIN minutes checks every file; if DoodStream deleted
  one, it is uploaded again from the Telegram copy with the SAME NAME.
* Permanent bot links never change:
    /d/<file_id>   DoodStream page      /de/<file_id>  embed
    /dv/<file_id>  real video for any video player / URL-stream app
"""
import asyncio
import logging
import random
import re
import string
import time
from urllib.parse import quote, urlparse

import aiohttp

from config import (
    FQDN, DOODSTREAM_KEY, DOODSTREAM_DOMAIN,
    HEAL_INTERVAL_MIN, UPLOAD_TIMEOUT_MIN, UPLOAD_PARALLEL,
)
from database import doodstream_db as db

logger = logging.getLogger(__name__)

API = "https://doodapi.co/api"
enabled = bool(DOODSTREAM_KEY)
REFERER = f"https://{DOODSTREAM_DOMAIN}/"
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"

_locks = {}
_upload_sem = asyncio.Semaphore(UPLOAD_PARALLEL)
MAX_FAILS = 5


def _base():
    return FQDN.replace("https://", "").replace("http://", "").strip().strip("/")


def dl_link(file_id):
    return f"https://{_base()}/dl/{file_id}"


def stable_link(file_id, embed=False):
    return f"https://{_base()}/{'de' if embed else 'd'}/{file_id}"


def video_link(file_id, name=None):
    """Direct-video link for any video player / app. Never changes."""
    n = (name or "video.mp4").replace("/", "_")
    if "." not in n[-6:]:
        n += ".mp4"
    return f"https://{_base()}/dv/{file_id}/{quote(n)}"


def dood_url(code, embed=False):
    return f"https://{DOODSTREAM_DOMAIN}/{'e' if embed else 'd'}/{code}"


def make_name(name, mime, file_id):
    name = (name or "").strip()
    if not name:
        ext = ".mp4" if "video" in (mime or "") else ".bin"
        name = f"{file_id}{ext}"
    return name


async def _api(path, **params):
    params["key"] = DOODSTREAM_KEY
    params = {k: v for k, v in params.items() if v not in (None, "")}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(f"{API}{path}", params=params) as r:
            return await r.json(content_type=None)


def _row_code(row, fallback=None):
    return str(row.get("filecode") or row.get("file_code") or fallback or "")


async def file_status(codes):
    """{code: http-like status}. Codes are left out when the API call itself failed."""
    out = {}
    for i in range(0, len(codes), 50):
        chunk = codes[i:i + 50]
        try:
            j = await _api("/file/info", file_code=",".join(chunk))
        except Exception as e:
            logger.warning(f"[doodstream] info error: {e}")
            continue
        if j.get("status") != 200:
            if j.get("status") == 404 and len(chunk) == 1:
                out[chunk[0]] = 404
            continue  # bad key / rate limit / 5xx: unknown, never treated as deleted
        rows = j.get("result") or []
        if isinstance(rows, dict):
            rows = [rows]
        by_code = {_row_code(r): r for r in rows if _row_code(r)}
        for idx, c in enumerate(chunk):
            r = by_code.get(c) or (rows[idx] if len(rows) == len(chunk) and not by_code else None)
            out[c] = int((r or {}).get("status", 404))
    return out


async def _remote_upload(file_id, name):
    """Returns the new DoodStream file code, or None."""
    add = await _api("/upload/url", url=dl_link(file_id), new_title=name)
    code = (add.get("result") or {}).get("filecode") if isinstance(add.get("result"), dict) else None
    if add.get("status") != 200 or not code:
        logger.warning(f"[doodstream] upload/url failed for {file_id}: {add.get('msg') or add.get('status')}")
        return None
    code = str(code)

    deadline = time.time() + UPLOAD_TIMEOUT_MIN * 60
    while time.time() < deadline:
        await asyncio.sleep(15)
        st = await file_status([code])
        if st.get(code) == 200:
            return code
        # still not ready: ask the remote-upload queue whether it failed
        try:
            j = await _api("/urlupload/status", file_code=code)
            rows = j.get("result") or []
            if isinstance(rows, dict):
                rows = [rows]
            for r in rows:
                state = str(r.get("status", ""))
                if re.search(r"error|fail", state, re.I):
                    logger.warning(f"[doodstream] remote upload failed for {file_id}: {state}")
                    try:
                        await _api("/urlupload/actions", delete_code=code)
                    except Exception:
                        pass
                    return None
        except Exception as e:
            logger.warning(f"[doodstream] status check error: {e}")
    logger.warning(f"[doodstream] upload timed out for {file_id}")
    return None


async def upload(file_id, name, mime=None, healing=False):
    """Upload (or re-upload) one bot file. Returns the DoodStream code or None."""
    if not enabled:
        return None
    lock = _locks.setdefault(int(file_id), asyncio.Lock())
    if lock.locked():
        return None
    async with lock:
        rec = await db.get(file_id)
        name = (rec or {}).get("name") or make_name(name, mime, file_id)
        await db.upsert(file_id, name=name, status="uploading")
        async with _upload_sem:
            try:
                new_id = await _remote_upload(file_id, name)
            except Exception as e:
                logger.error(f"[doodstream] upload error {file_id}: {e}")
                new_id = None
        if new_id:
            await db.upsert(file_id, st_id=new_id, status="ok", fails=0, last_check=time.time())
            if healing:
                await db.inc(file_id, healed=1)
            logger.info(f"[doodstream] {'restored' if healing else 'uploaded'} {file_id} -> {new_id} ({name})")
            return new_id
        await db.upsert(file_id, status="failed")
        await db.inc(file_id, fails=1)
        return None


_direct_cache = {}   # code -> (url, referer, expires_at)
_direct_locks = {}


def forget_direct(code):
    _direct_cache.pop(code, None)


async def direct_url(code, fresh=False):
    """
    Real video URL for a DoodStream file. DoodStream has no official direct-link API, so this
    reads the embed page the way the web player does (pass_md5 + token). Cached for 20 minutes.
    Returns the URL or None.
    """
    if fresh:
        forget_direct(code)
    hit = _direct_cache.get(code)
    if hit and hit[2] > time.time():
        return hit[0]
    lock = _direct_locks.setdefault(code, asyncio.Lock())
    async with lock:
        hit = _direct_cache.get(code)
        if hit and hit[2] > time.time():
            return hit[0]
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": UA}) as s:
                async with s.get(dood_url(code, embed=True), headers={"Referer": REFERER}) as r:
                    html = await r.text()
                    host = urlparse(str(r.url))
                    origin = f"{host.scheme}://{host.netloc}"
                m = re.search(r"/pass_md5/[^'\"\s]+", html)
                if not m:
                    logger.warning(f"[doodstream] pass_md5 not found for {code} (page blocked or changed)")
                    return None
                path = m.group(0)
                token = path.rstrip("/").split("/")[-1]
                async with s.get(origin + path, headers={"Referer": f"{origin}/e/{code}"}) as r2:
                    base = (await r2.text()).strip()
                if not base.startswith("http"):
                    logger.warning(f"[doodstream] bad pass_md5 reply for {code}: {base[:80]}")
                    return None
            rnd = "".join(random.choices(string.ascii_letters + string.digits, k=10))
            url = f"{base}{rnd}?token={token}&expiry={int(time.time() * 1000)}"
            _direct_cache[code] = (url, origin + "/", time.time() + 1200)
            return url
        except Exception as e:
            logger.error(f"[doodstream] direct url error {code}: {e}")
            return None


def direct_referer(code):
    hit = _direct_cache.get(code)
    return hit[1] if hit else REFERER


async def is_alive(file_id):
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
    await asyncio.sleep(45)
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
                    logger.info(f"[doodstream] {r['file_id']} ({r.get('name')}) was deleted - restoring")
                    await db.upsert(r["file_id"], status="failed", fails=0)
                    await heal_one(r["file_id"])
            for r in recs:
                stale = r.get("status") == "uploading" and time.time() - r.get("updated", 0) > UPLOAD_TIMEOUT_MIN * 60
                if (r.get("status") == "failed" or stale) and r.get("fails", 0) < MAX_FAILS:
                    await heal_one(r["file_id"])
        except Exception as e:
            logger.error(f"[doodstream] heal loop error: {e}")
        await asyncio.sleep(HEAL_INTERVAL_MIN * 60)
      
