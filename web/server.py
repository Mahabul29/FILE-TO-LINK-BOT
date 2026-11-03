import logging
from aiohttp import web
from config import PORT
from web.dl import download_handler
from web.streamtape_redirect import stable_redirect, stable_info, stable_video

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _alive(request):
    return web.Response(text="Bot is running")


async def web_server(bot_client):
    app = web.Application(client_max_size=30 * 1024 * 1024)
    app["bot_client"] = bot_client

    app.router.add_get("/", _alive)
    # Only used by Streamtape to pull the file from Telegram (remote upload)
    app.router.add_get("/dl/{file_id}", download_handler)
    # Your permanent links -> Streamtape
    app.router.add_get("/s/{file_id}", stable_redirect)
    app.router.add_get("/se/{file_id}", stable_redirect)
    app.router.add_get("/sinfo/{file_id}", stable_info)
    app.router.add_get("/sv/{file_id}", stable_video)
    app.router.add_get("/sv/{file_id}/{filename:.*}", stable_video)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(PORT))
    await site.start()
    logger.info(f"✅ Web server started on port {PORT}")
    return runner
    
