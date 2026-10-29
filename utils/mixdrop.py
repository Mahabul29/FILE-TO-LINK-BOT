"""
Mixdrop integration (same idea as utils/streamtape.py and utils/doodstream.py).

* upload(): Mixdrop downloads the file from this bot's /dl/<id> link (remote upload)
* heal_loop(): every HEAL_INTERVAL_MIN minutes checks every file; if Mixdrop deleted it,
  it is uploaded again from the Telegram copy with the SAME NAME.
* Permanent bot links never change:
    /m/<file_id>   Mixdrop page      /me/<file_id>  embed
    /mv/<file_id>  real video for any video player / URL-stream app
"""
import asyncio
import logging
import re
import time
from urllib.parse import quote

import aiohttp

from config import (
    FQDN, MIXDROP_EMAIL, MIXDROP_KEY, MIXDROP_DOMAIN,
    HEAL_INTERVAL_MIN, UPLOAD_TIMEOUT_MIN, UPLOAD_PARALLEL,
)
from database import mixdrop_db as db

logger = logging.getLogger(__name__)

API = "https://api.mixdrop.ag"
enabled = bool(MIXDROP_EMAIL and MIXDROP_KEY)
REFERER = f"https://{MIXDROP_DOMAIN}/"
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"

_locks = {}
_upload_sem = asyncio.Semaphore(UPLOAD_PARALLEL)
MAX_FAILS = 5


def _base():
    return FQDN.replace("https://", "").replace("http://", "").strip().strip("/")


def dl_link(file_id):
    return f"https://{_base()}/dl/{file_id}"


def stable_link(file_id, embed=False):
    return f"https://{_base()}/{'me' if embed else 'm'}/{file_id}"


def video_link(file_id, name=None):
    """Direct-video link for any video player / app. Never changes."""
    n = (name or "video.mp4").replace("/", "_")
    if "." not in n[-6:]:
        n += ".mp4"
    return f"https://{_base()}/mv/{file_id}/{quote(n)}"


def mix_url(ref, embed=False):
    return f"https://{MIXDROP_DOMAIN}/{'e' if embed else 'f'}/{ref}"


def make_name(name, mime, file_id):
    name = (name or "").strip()
    if not name:
        ext = ".mp4" if "video" in (mime or "") else ".bin"
        name = f"{file_id}{ext}"
    return name


async def _api(path, params):
    """params: list of (key, value) so ref[] can repeat."""
    q = [("email", MIXDROP_EMAIL), ("key", MIXDROP_KEY)] + [(k, v) for k, v in params if v not in (None, "")]
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(f"{API}{path}", params=q) as r:
            return await r.json(content_type=None)


async def file_status(refs):
    """
    {ref: 200 (ready) | 404 (gone) | 202 (still uploading/converting)}.
    Refs are left out when the API call itself failed (never treated as deleted).
    """
    out = {}
    for i in range(0, len(refs), 50):
        chunk = refs[i:i + 50]
        try:
            j = await _api("/fileinfo2", [("ref[]", r) for r in chunk])
        except Exception as e:
            logger.warning(f"[mixdrop] info error: {e}")
            continue
        if not j.get("success") or not isinstance(j.get("result"), dict):
            continue  # bad key / rate limit: unknown
        for ref in chunk:
            row = j["result"].get(ref)
            if row is None:
                continue
            st = str(row.get("status", ""))
            if row.get("deleted") or st.lower() == "notfound":
                out[ref] = 404
            elif st.upper() == "OK":
                out[ref] = 200
            else:
                out[ref] = 202
    return out


async def _remote_upload(file_id, name):
    """Returns the new Mixdrop file ref, or None."""
    add = await _api("/remoteupload", [("url", dl_link(file_id)), ("name", name)])
    res = add.get("result") if isinstance(add.get("result"), dict) else {}
    rid, ref = res.get("id"), res.get("fileref")
    if not add.get("success") or not rid:
        logger.warning(f"[mixdrop] remoteupload failed for {file_id}: {add}")
        return None

    deadline = time.time() + UPLOAD_TIMEOUT_MIN * 60
    while time.time() < deadline:
        await asyncio.sleep(15)
        try:
            j = await _api("/remotestatus", [("id", rid)])
        except Exception as e:
            logger.warning(f"[mixdrop] status check error: {e}")
            continue
        row = j.get("result") if isinstance(j.get("result"), dict) else {}
        ref = row.get("fileref") or ref
        state = str(row.get("status", ""))
        if re.search(r"error|fail", state, re.I):
            logger.warning(f"[mixdrop] remote upload failed for {file_id}: {row.get('error') or state}")
            return None
        if re.search(r"complete", state, re.I) and ref:
            return str(ref)
    logger.warning(f"[mixdrop] upload timed out for {file_id}")
    return None


async def upload(file_id, name, mime=None, healing=False):
    """Upload (or re-upload) one bot file. Returns the Mixdrop ref or None."""
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
                logger.error(f"[mixdrop] upload error {file_id}: {e}")
                new_id = None
        if new_id:
            await db.upsert(file_id, st_id=new_id, status="ok", fails=0, last_check=time.time())
            if healing:
                await db.inc(file_id, healed=1)
            logger.info(f"[mixdrop] {'restored' if healing else 'uploaded'} {file_id} -> {new_id} ({name})")
            return new_id
        await db.upsert(file_id, status="failed")
        await db.inc(file_id, fails=1)
        return None


# ---- direct video URL (Mixdrop has no direct-link API: read the embed page like the web player) ----

_B62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _to_base(n, b):
    if n == 0:
        return "0"
    s = ""
    while n:
        s = _B62[n % b] + s
        n //= b
    return s


def _unpack(payload, base, count, words):
    """Undo Dean Edwards' p.a.c.k.e.r. JavaScript packing."""
    table = {}
    for i in range(count):
        key = _to_base(i, base)
        table[key] = words[i] if i < len(words) and words[i] else key
    return re.sub(r"\b\w+\b", lambda m: table.get(m.group(0), m.group(0)), payload)


def _find_video_url(html):
    """Returns the video URL found in an embed page (plain or packed), or None."""
    m = re.search(r'wurl\s*=\s*["\']([^"\']+)["\']', html)
    if not m:
        for pm in re.finditer(r"\}\('((?:[^'\\]|\\.)*)',\s*(\d+),\s*(\d+),\s*'((?:[^'\\]|\\.)*)'\.split\('\|'\)", html, re.S):
            payload = pm.group(1).replace("\\'", "'").replace("\\\\", "\\")
            words = pm.group(4).replace("\\'", "'").split("|")
            text = _unpack(payload, int(pm.group(2)), int(pm.group(3)), words)
            m = re.search(r'wurl\s*=\s*["\']([^"\']+)["\']', text)
            if m:
                break
    if not m:
        return None
    url = m.group(1)
    if url.startswith("//"):
        url = "https:" + url
    return url if url.startswith("http") else None


_direct_cache = {}   # ref -> (url, referer, expires_at)
_direct_locks = {}


def forget_direct(ref):
    _direct_cache.pop(ref, None)


async def direct_url(ref, fresh=False):
    """Real video URL for a Mixdrop file, cached for 20 minutes. Returns the URL or None."""
    if fresh:
        forget_direct(ref)
    hit = _direct_cache.get(ref)
    if hit and hit[2] > time.time():
        return hit[0]
    lock = _direct_locks.setdefault(ref, asyncio.Lock())
    async with lock:
        hit = _direct_cache.get(ref)
        if hit and hit[2] > time.time():
            return hit[0]
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": UA}) as s:
                async with s.get(mix_url(ref, embed=True), headers={"Referer": REFERER}) as r:
                    html = await r.text()
                    origin = f"{r.url.scheme}://{r.url.host}"
            url = _find_video_url(html)
            if not url:
                logger.warning(f"[mixdrop] video url not found for {ref} (page blocked or changed)")
                return None
            _direct_cache[ref] = (url, origin + "/", time.time() + 1200)
            return url
        except Exception as e:
            logger.error(f"[mixdrop] direct url error {ref}: {e}")
            return None


def direct_referer(ref):
    hit = _direct_cache.get(ref)
    return hit[1] if hit else REFERER


async def is_alive(file_id):
    """True / False, or None if unknown (also None while the file is still converting)."""
    rec = await db.get(file_id)
    if not rec or not rec.get("st_id"):
        return None
    if time.time() - rec.get("last_check", 0) < 600:
        return rec.get("status") == "ok"
    st = await file_status([rec["st_id"]])
    code = st.get(rec["st_id"])
    if code not in (200, 404):
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
    await asyncio.sleep(60)
    while True:
        try:
            recs = await db.all_records()
            ok = [r for r in recs if r.get("status") == "ok" and r.get("st_id")]
            status = await file_status([r["st_id"] for r in ok])
            for r in ok:
                code = status.get(r["st_id"])
                if code == 200:
                    await db.upsert(r["file_id"], last_check=time.time())
                elif code == 404:
                    logger.info(f"[mixdrop] {r['file_id']} ({r.get('name')}) was deleted - restoring")
                    await db.upsert(r["file_id"], status="failed", fails=0)
                    await heal_one(r["file_id"])
            for r in recs:
                stale = r.get("status") == "uploading" and time.time() - r.get("updated", 0) > UPLOAD_TIMEOUT_MIN * 60
                if (r.get("status") == "failed" or stale) and r.get("fails", 0) < MAX_FAILS:
                    await heal_one(r["file_id"])
        except Exception as e:
            logger.error(f"[mixdrop] heal loop error: {e}")
        await asyncio.sleep(HEAL_INTERVAL_MIN * 60)
