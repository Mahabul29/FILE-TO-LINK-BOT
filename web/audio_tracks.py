import asyncio
import json
import logging

from aiohttp import web
from config import PORT

logger = logging.getLogger(__name__)


def _internal_stream_url(file_id):
    # Probe/extract from our own stream route over localhost so ffmpeg/ffprobe
    # can use HTTP range requests (seeking) without an extra public round trip.
    return f"http://127.0.0.1:{PORT}/stream/{file_id}"


async def tracks_handler(request):
    """
    GET /tracks/{file_id}
    Returns {"tracks": [{"index": 0, "label": "..."}], ...]}
    index 0 always means "file's default/native audio" (no extraction needed).
    """
    file_id = request.match_info.get("file_id")
    source_url = _internal_stream_url(file_id)

    cmd = [
        "ffprobe", "-v", "error",
        "-seekable", "1",
        "-print_format", "json",
        "-show_streams",
        source_url,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        if proc.returncode != 0:
            logger.error(f"ffprobe failed for {file_id}: {stderr.decode(errors='ignore')}")
            return web.json_response({"tracks": []})

        data = json.loads(stdout.decode(errors="ignore") or "{}")
        audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]

        tracks = []
        for i, s in enumerate(audio_streams):
            tags = s.get("tags", {}) or {}
            lang = tags.get("language", "")
            title = tags.get("title", "")
            label = title or lang or f"Audio {i + 1}"
            tracks.append({"index": i, "label": label, "codec": s.get("codec_name", "")})

        return web.json_response({"tracks": tracks})

    except asyncio.TimeoutError:
        logger.error(f"ffprobe timed out for {file_id}")
        return web.json_response({"tracks": []})
    except FileNotFoundError:
        logger.error("ffprobe not found — install ffmpeg on this deployment")
        return web.json_response({"tracks": []})
    except Exception as e:
        logger.error(f"tracks_handler error: {e}")
        return web.json_response({"tracks": []})


async def audio_track_handler(request):
    """
    GET /audio/{file_id}/{track_index}
    Streams the selected audio track only, stream-copied (no re-encode) into
    a fragmented mp4 container so it can be played directly by <audio src=...>.
    """
    file_id = request.match_info.get("file_id")
    try:
        track_index = int(request.match_info.get("track_index"))
    except (TypeError, ValueError):
        return web.Response(text="❌ Invalid track index", status=400)

    source_url = _internal_stream_url(file_id)

    cmd = [
        "ffmpeg", "-v", "error",
        "-seekable", "1",
        "-i", source_url,
        "-map", f"0:a:{track_index}",
        "-c:a", "copy",
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "pipe:1",
    ]

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "audio/mp4",
                "Cache-Control": "no-store",
            },
        )
        await response.prepare(request)

        while True:
            chunk = await proc.stdout.read(65536)
            if not chunk:
                break
            await response.write(chunk)

        await response.write_eof()
        return response

    except (asyncio.CancelledError, ConnectionResetError):
        # Client closed the player / switched tracks — expected, just clean up.
        raise
    except FileNotFoundError:
        logger.error("ffmpeg not found — install ffmpeg on this deployment")
        return web.Response(text="❌ ffmpeg not available on server", status=500)
    except Exception as e:
        logger.error(f"audio_track_handler error: {e}")
        return web.Response(text=f"❌ Error: {e}", status=500)
    finally:
        if proc and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
