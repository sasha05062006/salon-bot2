import asyncio
import importlib
import logging

logging.basicConfig(level=logging.INFO)

async def run():
    try:
        main_module = importlib.import_module("main")
        await main_module.main()
    except BaseException:
        logging.exception("Main application failed; starting maintenance server")
        from maintenance_server import main as maintenance_main
        await maintenance_main()

if __name__ == "__main__":
    asyncio.run(run())
