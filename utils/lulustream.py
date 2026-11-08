"""
LuluStream integration (runs next to utils/streamtape.py).

* upload(): LuluStream downloads the file from this bot's /dl/<id> link (upload by URL),
  then the title is set to the SAME name used on Streamtape.
* heal_loop(): every HEAL_INTERVAL_MIN minutes checks every LuluStream file. If it was
  deleted, the bot uploads it again from the Telegram BIN_CHANNEL copy with the SAME NAME.
* The bot's permanent link https://<FQDN>/s/<file_id> never changes. It opens Streamtape,
  and if Streamtape lost the file it opens LuluStream instead (see web/streamtape_redirect.py).

Data is kept on the same Mongo row as Streamtape (database/streamtape_db.py) in separate
fields: lulu_id, lulu_status (uploading | ok | failed), lulu_fails, lulu_healed, lulu_updated.
"""
import asyncio
import logging
import re
import time

import aiohttp

from config import (
    LULUSTREAM_KEY, LULUSTREAM_FOLDER, LULUSTREAM_DOMAIN, LULUSTREAM_BACKFILL, LULUSTREAM_API,
    HEAL_INTERVAL_MIN, UPLOAD_TIMEOUT_MIN, UPLOAD_PARALLEL,
)
from database import streamtape_db as db
from utils.streamtape import dl_link, make_name

logger = logging.getLogger(__name__)

API = LULUSTREAM_API
enabled = bool(LULUSTREAM_KEY)

last_error = {}   # file_id -> short reason of the last failed upload (shown in the bot message)
_locks = {}
_upload_sem = asyncio.Semaphore(UPLOAD_PARALLEL)
MAX_FAILS = 5
GIVE_UP_RETRY_HOURS = 6


def page_url(code, embed=False):
    return f"https://{LULUSTREAM_DOMAIN}/{'e/' if embed else ''}{code}"


async def _set(file_id, **fields):
    # own timestamp, so Streamtape's retry timing (row["updated"]) is never disturbed
    fields["lulu_updated"] = time.time()
    await db.col.update_one({"file_id": int(file_id)}, {"$set": fields}, upsert=True)


async def _inc(file_id, **counters):
    await db.col.update_one({"file_id": int(file_id)}, {"$inc": counters})


async def _api(path, **params):
    params["key"] = LULUSTREAM_KEY
    params = {k: v for k, v in params.items() if v not in (None, "")}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(f"{API}{path}", params=params) as r:
            return await r.json(content_type=None)


async def file_status(codes):
    """{file_code: http-like status}. Codes are left out when the API call itself failed."""
    out = {}
    for i in range(0, len(codes), 100):
        chunk = codes[i:i + 100]
        try:
            j = await _api("/file/info", file_code=",".join(chunk))
        except Exception as e:
            logger.warning(f"[lulustream] info error: {e}")
            continue
        if j.get("status") == 200 and isinstance(j.get("result"), list):
            got = {}
            for r in j["result"]:
                if not isinstance(r, dict):
                    continue
                # the API may call the field "file_code" or "filecode"
                rc = r.get("file_code") or r.get("filecode")
                if not rc:
                    continue
                try:
                    got[str(rc)] = int(r.get("status", 404))
                except (TypeError, ValueError):
                    pass
            if not got and j["result"]:
                # answer came back in a shape we cannot read: unknown, NEVER "deleted"
                logger.warning(f"[lulustream] info answer not understood: {str(j['result'])[:200]}")
                continue
            for c in chunk:
                out[c] = got.get(c, 404)
        elif j.get("status") == 404 and len(chunk) == 1:
            out[chunk[0]] = 404
        # any other answer (rate limit, 5xx, bad key) = unknown, never treated as deleted
    return out


async def _cleanup_failed(code):
    try:
        await _api("/file/url_actions", delete_code=code)
    except Exception:
        pass


def _row_is_mine(row, code, file_id):
    if not isinstance(row, dict):
        return False
    for k in ("file_code", "filecode", "code"):
        if str(row.get(k) or "") == str(code):
            return True
    return f"/dl/{file_id}" in " ".join(str(v) for v in row.values())


async def _remote_upload(file_id, name):
    """Returns the LuluStream file code once the file exists, or None."""
    add = await _api("/upload/url", url=dl_link(file_id), fld_id=LULUSTREAM_FOLDER)
    res = add.get("result")
    code = res.get("filecode") if isinstance(res, dict) else None
    if add.get("status") != 200 or not code:
        logger.warning(f"[lulustream] upload/url failed for {file_id}: {add.get('msg') or add.get('status')}")
        last_error[int(file_id)] = f"upload/url: {add.get('msg') or add.get('status')}"[:120]
        return None

    deadline = time.time() + UPLOAD_TIMEOUT_MIN * 60
    while time.time() < deadline:
        await asyncio.sleep(10)
        try:
            if (await file_status([code])).get(code) == 200:
                try:
                    await _api("/file/edit", file_code=code, file_title=name)  # same name as Streamtape
                except Exception as e:
                    logger.warning(f"[lulustream] rename failed for {code}: {e}")
                return code
            q = await _api("/file/url_uploads", file_code=code)
            rows = q.get("result") if isinstance(q.get("result"), list) else []
            # the queue lists every remote upload of the account: look only at OUR row
            rows = [r for r in rows if _row_is_mine(r, code, file_id)]
            if any(re.search(r"error|fail", str(r.get("status", "")), re.I) for r in rows):
                logger.warning(f"[lulustream] remote upload failed for {file_id}")
                last_error[int(file_id)] = f"remote upload: {str(rows)[:100]}"
                await _cleanup_failed(code)
                return None
        except Exception as e:
            logger.warning(f"[lulustream] status check error: {e}")
    logger.warning(f"[lulustream] upload timed out for {file_id}")
    last_error[int(file_id)] = "timed out"
    await _cleanup_failed(code)
    return None


async def upload(file_id, name, mime=None, healing=False):
    """Upload (or re-upload) one bot file. Returns the LuluStream code or None."""
    if not enabled:
        return None
    lock = _locks.setdefault(int(file_id), asyncio.Lock())
    if lock.locked():
        return None
    async with lock:
        rec = await db.get(file_id)
        name = (rec or {}).get("name") or make_name(name, mime, file_id)
        await _set(file_id, name=name, lulu_status="uploading")
        async with _upload_sem:
            try:
                code = await _remote_upload(file_id, name)
            except Exception as e:
                logger.error(f"[lulustream] upload error {file_id}: {e}")
                last_error[int(file_id)] = f"error: {e}"[:120]
                code = None
        if code:
            await _set(file_id, lulu_id=code, lulu_status="ok", lulu_fails=0, lulu_last_check=time.time())
            if healing:
                await _inc(file_id, lulu_healed=1)
            logger.info(f"[lulustream] {'restored' if healing else 'uploaded'} {file_id} -> {code} ({name})")
            return code
        await _set(file_id, lulu_status="failed")
        await _inc(file_id, lulu_fails=1)
        return None


async def mark_failed(file_id):
    await _set(file_id, lulu_status="failed", lulu_fails=0)


_direct_cache = {}   # code -> (url, expires_at)
_direct_locks = {}


def forget_direct(code):
    _direct_cache.pop(code, None)


async def direct_url(code, fresh=False):
    """Real mp4 URL from LuluStream (needs the Direct Link feature on the account). Cached 30 min."""
    if fresh:
        forget_direct(code)
    hit = _direct_cache.get(code)
    if hit and hit[1] > time.time():
        return hit[0]
    lock = _direct_locks.setdefault(code, asyncio.Lock())
    async with lock:
        hit = _direct_cache.get(code)
        if hit and hit[1] > time.time():
            return hit[0]
        try:
            j = await _api("/file/direct_link", file_code=code)
            res = j.get("result")
            versions = (res.get("versions") if isinstance(res, dict) else None) or []
            if j.get("status") != 200 or not versions:
                logger.warning(f"[lulustream] direct_link failed for {code}: {j.get('msg') or j.get('status')}")
                return None
            best = next((v for v in versions if v.get("name") == "n"), versions[0])
            url = best.get("url")
            if not url:
                return None
            _direct_cache[code] = (url, time.time() + 1800)
            return url
        except Exception as e:
            logger.error(f"[lulustream] direct url error {code}: {e}")
            return None


async def is_alive(file_id):
    """True / False, or None if unknown. Cached for 10 minutes in the DB row."""
    rec = await db.get(file_id)
    if not rec or not rec.get("lulu_id"):
        return None
    if time.time() - rec.get("lulu_last_check", 0) < 600:
        return rec.get("lulu_status") == "ok"
    code = (await file_status([rec["lulu_id"]])).get(rec["lulu_id"])
    if code is None:
        return None
    await _set(file_id, lulu_last_check=time.time())
    return code == 200


async def heal_one(file_id):
    rec = await db.get(file_id)
    if not rec:
        return None
    return await upload(file_id, rec.get("name"), healing=True)


async def heal_loop():
    """Background task: finds files LuluStream deleted and uploads them again."""
    await asyncio.sleep(45)
    while True:
        try:
            recs = await db.all_records()
            ok = [r for r in recs if r.get("lulu_status") == "ok" and r.get("lulu_id")]
            status = await file_status([r["lulu_id"] for r in ok])
            for r in ok:
                code = status.get(r["lulu_id"])
                if code is None:
                    continue
                if code == 200:
                    await _set(r["file_id"], lulu_last_check=time.time())
                elif code == 404:
                    logger.info(f"[lulustream] {r['file_id']} ({r.get('name')}) was deleted - restoring")
                    await mark_failed(r["file_id"])
                    await heal_one(r["file_id"])
            for r in recs:
                st = r.get("lulu_status")
                if st is None:
                    # old file from before LuluStream was added: only when LULUSTREAM_BACKFILL=true
                    if LULUSTREAM_BACKFILL and r.get("name"):
                        await heal_one(r["file_id"])
                    continue
                stale = st == "uploading" and time.time() - r.get("lulu_updated", 0) > UPLOAD_TIMEOUT_MIN * 60
                if not (st == "failed" or stale):
                    continue
                cooled = time.time() - r.get("lulu_updated", 0) > GIVE_UP_RETRY_HOURS * 3600
                if r.get("lulu_fails", 0) < MAX_FAILS or cooled:
                    await heal_one(r["file_id"])
        except Exception as e:
            logger.error(f"[lulustream] heal loop error: {e}")
        await asyncio.sleep(HEAL_INTERVAL_MIN * 60)
      
