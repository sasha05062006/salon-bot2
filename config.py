import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


SETUP_COMMAND = os.getenv("SETUP_COMMAND", "/salon_setup")
