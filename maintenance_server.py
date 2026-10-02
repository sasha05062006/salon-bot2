import asyncio
import logging
import os
from aiohttp import web

logging.basicConfig(level=logging.INFO)

HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Технические работы</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0f1115;color:#fff;font-family:system-ui,-apple-system,sans-serif;padding:24px;box-sizing:border-box}
.box{text-align:center;max-width:420px;padding:32px;border:1px solid #292d36;border-radius:24px;background:#171a21}
.icon{font-size:48px;margin-bottom:12px}h1{font-size:24px;margin:0 0 12px}p{color:#aeb4c0;line-height:1.5;margin:8px 0}
</style></head><body><main class="box"><div class="icon">🛠️</div>
<h1>Ведутся технические работы</h1>
<p>Приложение временно недоступно.</p>
<p>Мы уже занимаемся восстановлением работы. Пожалуйста, попробуйте зайти немного позже.</p>
</main></body></html>"""

async def maintenance(request):
    return web.Response(text=HTML, content_type="text/html", status=503)

async def health(request):
    return web.json_response({"ok": False, "maintenance": True}, status=503)

async def main():
    app=web.Application()
    app.router.add_get("/", maintenance)
    app.router.add_get("/maintenance", maintenance)
    app.router.add_get("/health", health)
    host=os.getenv("WEBAPP_HOST","0.0.0.0")
    port=int(os.getenv("PORT") or os.getenv("WEBAPP_PORT","8080"))
    runner=web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner,host,port).start()
    logging.info("Maintenance server listening on %s:%s",host,port)
    while True:
        await asyncio.sleep(3600)

if __name__=="__main__":
    asyncio.run(main())
