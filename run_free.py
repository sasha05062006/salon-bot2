import asyncio
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from urllib.request import urlopen, Request

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
PORT = int(os.getenv("WEBAPP_PORT", "8080"))
TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")

def find_cloudflared():
    p = shutil.which("cloudflared")
    if p:
        return p
    local = ROOT / "cloudflared.exe"
    if local.exists():
        return str(local)
    return None

def main():
    if not TOKEN or not ADMIN_ID:
        print("ERROR: BOT_TOKEN and ADMIN_ID must be set in .env")
        sys.exit(1)

    cloudflared = find_cloudflared()
    if not cloudflared:
        print("ERROR: cloudflared is not installed.")
        print("Install it free with: winget install Cloudflare.cloudflared")
        print("Then run this file again.")
        sys.exit(1)

    print("Starting free Telegram Mini App tunnel...")
    tunnel = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://127.0.0.1:{PORT}", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", bufsize=1
    )

    url = None
    deadline = time.time() + 30
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    while time.time() < deadline:
        line = tunnel.stdout.readline()
        if line:
            print("[cloudflared]", line.strip())
            m = pattern.search(line)
            if m:
                url = m.group(0)
                break
        elif tunnel.poll() is not None:
            break

    if not url:
        tunnel.terminate()
        print("ERROR: Could not obtain a trycloudflare.com URL.")
        sys.exit(1)

    print("Mini App URL:", url)
    print("Starting bot...")
    env = os.environ.copy()
    env["WEBAPP_URL"] = url
    subprocess.run([sys.executable, str(ROOT / "main.py")], env=env)

    tunnel.terminate()
    try:
        tunnel.wait(timeout=5)
    except subprocess.TimeoutExpired:
        tunnel.kill()

if __name__ == "__main__":
    main()
