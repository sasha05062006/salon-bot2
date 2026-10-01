import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Railway supplies RAILWAY_PUBLIC_DOMAIN after a public domain is generated.
# WEBAPP_URL can override it when a custom/public URL is used.
_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip().rstrip("/")
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/") or (
    f"https://{_railway_domain}" if _railway_domain else ""
)

WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("PORT") or os.getenv("WEBAPP_PORT") or "8080")

SETUP_COMMAND = os.getenv("SETUP_COMMAND", "/salon_setup")
