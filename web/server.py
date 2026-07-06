import logging
from aiohttp import web
from config import PORT
from web.video_play import video_play, stream_handler, download_handler
from web.home import home_page

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def web_server(bot_client):
    app = web.Application(client_max_size=30 * 1024 * 1024)
    app["bot_client"] = bot_client

    app.router.add_get("/", home_page)
    app.router.add_get("/watch/{file_id}", video_play)
    app.router.add_get("/stream/{file_id}", stream_handler)
    app.router.add_get("/dl/{file_id}", download_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(PORT))
    await site.start()
    logger.info(f"✅ Web server started on port {PORT}")
    return runner
