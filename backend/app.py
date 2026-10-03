import os
from pathlib import Path
from aiohttp import web

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
PORT = int(os.getenv("PORT", "8080"))

async def health(request):
    return web.json_response({"ok": True, "service": "salon-pwa"})

async def config(request):
    return web.json_response({"ok": True, "salon": {"name": "BeautySalon", "description": "Красота и удобство"}, "features": {"booking": True, "admin": True, "masters": True}})

async def index(request):
    response = web.FileResponse(FRONTEND / "index.html")
    response.headers["Cache-Control"] = "no-store"
    return response

async def static_file(request):
    path = FRONTEND / request.match_info["name"]
    if not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)

def create_app():
    app = web.Application()
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/config", config)
    app.router.add_get("/", index)
    app.router.add_get("/manifest.webmanifest", static_file)
    app.router.add_get("/sw.js", static_file)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
