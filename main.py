import asyncio

# Python 3.12+/3.14 does not create an event loop automatically and Pyrogram
# needs one at import time, so create it BEFORE importing pyrogram.
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from bot import Bot  # noqa: E402


async def main():
    bot = Bot()
    await bot.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
      
