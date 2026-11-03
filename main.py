import asyncio

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from bot import Bot


async def main():
    bot = Bot()
    await bot.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
