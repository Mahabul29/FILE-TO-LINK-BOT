import asyncio

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from bot import Bot


async def main():
    bot = Bot()
    await bot.start()
    await asyncio.Event().wait()


loop.run_until_complete(main())
