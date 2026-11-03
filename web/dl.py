import asyncio
import logging
from urllib.parse import quote
from aiohttp import web
from config import BIN_CHANNEL

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
# /dl/<id> is the source link Streamtape pulls the file from (remote upload).
_DL_SEMAPHORE = asyncio.Semaphore(4)
DL_STALL_TIMEOUT = 45  # seconds without a chunk from Telegram before the transfer is aborted


def _content_disposition(kind, name):
    """Header-safe Content-Disposition (non-ASCII / quotes / newlines in the name no longer crash)."""
    name = (name or "file").replace("\r", "").replace("\n", "").replace('"', "'")
    ascii_name = name.encode("ascii", "ignore").decode() or "file"
    if ascii_name == name:
        return f'{kind}; filename="{ascii_name}"'
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8\'\'{quote(name)}"


def _parse_range(header, size):
    """'bytes=a-b' / 'bytes=a-' / 'bytes=-n' -> (start, end), or None if unsatisfiable."""
    try:
        unit, _, spec = header.strip().partition("=")
        if unit.strip().lower() != "bytes" or "," in spec:
            return None
        a, _, b = spec.strip().partition("-")
        if a == "":
            n = int(b)
            if n <= 0:
                return None
            return max(0, size - n), size - 1
        start = int(a)
        end = int(b) if b else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            return None
        return start, end
    except Exception:
        return None


def _media_info(media):
    file_name = getattr(media, "file_name", "Unknown File")
    mime_type = getattr(media, "mime_type", "application/octet-stream") or "application/octet-stream"
    file_size = getattr(media, "file_size", 0) or 0
    return file_name, mime_type, file_size


async def _get_media(bot_client, file_id):
    msg = await bot_client.get_messages(int(BIN_CHANNEL), int(file_id))
    media = msg.document or msg.video or msg.audio or msg.photo
    return msg, media


async def _chunked_stream(bot_client, msg, start: int, end: int):
    offset = start - (start % CHUNK_SIZE)
    first_cut = start - offset
    last_cut = (end % CHUNK_SIZE) + 1
    part_count = ((end - offset) // CHUNK_SIZE) + 1

    current = 0
    async for chunk in bot_client.stream_media(
        msg, offset=offset // CHUNK_SIZE, limit=part_count
    ):
        if part_count == 1:
            yield chunk[first_cut:last_cut]
        elif current == 0:
            yield chunk[first_cut:]
        elif current == part_count - 1:
            yield chunk[:last_cut]
        else:
            yield chunk
        current += 1


async def download_handler(request):
    """
    /dl/<id> - full file download. Also the source link remote-upload servers
    (Streamtape) pull from, so it must behave like a real file server:
      * HEAD answers headers only (no download from Telegram)
      * Range / resume supported (206), bad ranges get 416
      * a stalled Telegram transfer is aborted so the client sees an error and retries
    """
    file_id = request.match_info.get("file_id")
    bot_client = request.app["bot_client"]

    try:
        msg, media = await _get_media(bot_client, file_id)
        if not media:
            return web.Response(text="❌ File not found", status=404)

        file_name, mime_type, file_size = _media_info(media)

        start, end, status = 0, max(file_size - 1, 0), 200
        range_header = request.headers.get("Range")
        if range_header and file_size:
            parsed = _parse_range(range_header, file_size)
            if parsed is None:
                return web.Response(status=416, headers={"Content-Range": f"bytes */{file_size}"})
            start, end = parsed
            status = 206

        headers = {
            "Content-Type": mime_type if mime_type != "unknown" else "application/octet-stream",
            "Content-Disposition": _content_disposition("attachment", file_name),
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-store",
        }
        if file_size:
            headers["Content-Length"] = str(end - start + 1)
            if status == 206:
                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)

        if request.method == "HEAD" or not file_size:
            if request.method != "HEAD":
                async for chunk in bot_client.stream_media(msg):
                    await response.write(chunk)
            await response.write_eof()
            return response

        async with _DL_SEMAPHORE:
            gen = _chunked_stream(bot_client, msg, start, end)
            sent = 0
            try:
                while True:
                    try:
                        chunk = await asyncio.wait_for(gen.__anext__(), timeout=DL_STALL_TIMEOUT)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        logger.warning(f"/dl stalled (no data for {DL_STALL_TIMEOUT}s) on {file_id} at {start + sent}/{file_size}")
                        if request.transport:
                            request.transport.close()   # incomplete body -> client sees a real error
                        return response
                    if chunk:
                        await response.write(chunk)
                        sent += len(chunk)
            except (ConnectionResetError, asyncio.CancelledError):
                return response
            finally:
                try:
                    await gen.aclose()
                except Exception:
                    pass

        await response.write_eof()
        return response

    except Exception as e:
        logger.error(f"Download error: {e}")
        return web.Response(text=f"❌ Error: {e}", status=500)


    
