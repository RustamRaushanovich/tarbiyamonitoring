# -*- coding: utf-8 -*-
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import uvicorn
import asyncio
import threading

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from app.db import init_db
from app.bot.telegram_bot import start_bot

def _load_env():
    env_path = os.path.join(CURRENT_DIR, '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip()
        except Exception:
            pass

_load_env()

def run_telegram_bot_thread():
    if os.getenv("ENABLE_BOT", "false").lower() != "true":
        print("[Telegram Bot] Bot orqa fonda o'chirilgan (Render Davomat boti bilan to'qnashmasligi uchun). Web-platforma to'liq ishlaydi.")
        return
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_bot())
    except Exception as e:
        print(f"[Telegram Bot] Thread notice: {e}")

if __name__ == "__main__":
    print("==================================================================")
    print("🏛  FARG‘ONA VILOYATI MAKTABGACHA VA MAKTAB TA’LIMI BOSHQARMASI")
    print("    IJRO NAZORATI VA MONITORING AXBOROT PLATFORMASI (WEB + BOT)")
    print("==================================================================")

    init_db()

    # Start bot thread
    t = threading.Thread(target=run_telegram_bot_thread, daemon=True)
    t.start()

    port = int(os.getenv("PORT", 8080))
    print(f"Server ishga tushmoqda: http://127.0.0.1:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
