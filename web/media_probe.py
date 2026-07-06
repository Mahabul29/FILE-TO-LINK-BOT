import asyncio
import json
import logging
from config import BIN_CHANNEL

logger = logging.getLogger(__name__)

FFPROBE_BYTES_LIMIT = 15 * 1024 * 1024  # 15MB usually covers mkv track metadata


async def _feed_partial(bot_client, msg, proc, byte_limit=None):
    sent = 0
    try:
        async for chunk in bot_client.stream_media(msg):
            proc.stdin.write(chunk)
            await proc.stdin.drain()
            sent += len(chunk)
            if byte_limit and sent >= byte_limit:
                break
    except Exception as e:
        logger.warning(f"feed error: {e}")
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass


async def _feed_full(bot_client, msg, proc):
    try:
        async for chunk in bot_client.stream_media(msg):
            proc.stdin.write(chunk)
            await proc.stdin.drain()
    except Exception as e:
        logger.warning(f"feed error: {e}")
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass


async def probe_tracks(bot_client, file_id):
    """Returns {"audio": [{"index": n, "lang": "hin"}, ...], "subtitle": [...]}"""
    msg = await bot_client.get_messages(int(BIN_CHANNEL), int(file_id))
    media = msg.document or msg.video or msg.audio
    if not media:
        return {"audio": [], "subtitle": []}

    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-i", "pipe:0"]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    feed_task = asyncio.create_task(_feed_partial(bot_client, msg, proc, FFPROBE_BYTES_LIMIT))

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=40)
    except asyncio.TimeoutError:
        proc.kill()
        await feed_task
        return {"audio": [], "subtitle": []}

    await feed_task

    audio, subtitle = [], []
    try:
        data = json.loads(stdout.decode(errors="ignore"))
        for s in data.get("streams", []):
            idx = s.get("index")
            lang = s.get("tags", {}).get("language", f"Track {idx}")
            if s.get("codec_type") == "audio":
                audio.append({"index": idx, "lang": lang})
            elif s.get("codec_type") == "subtitle":
                subtitle.append({"index": idx, "lang": lang})
    except Exception as e:
        logger.error(f"probe parse error: {e}")

    return {"audio": audio, "subtitle": subtitle}
