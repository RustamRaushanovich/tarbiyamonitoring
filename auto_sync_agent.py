# -*- coding: utf-8 -*-
"""
AVTOMATIK SINXRONIZATSIYA AGENTI (AUTO-SYNC AGENT)
Farg'ona Viloyati Maktabgacha va Maktab Ta'limi Boshqarmasi
------------------------------------------------------------
Ushbu skript kompyuter yoqilishi bilan (yoki Windows avto-ishga tushishida) 
avtomatik ishga tushadi va tashqi/mahalliy serverga ulanib:
1. Tumanlar yuklagan barcha yangi dalil fayllarini
2. Eng oxirgi yangilangan 15-talik Viloyat Excel Kitobini
avtomatik tarzda sizning kompyuteringizdagi:
E:\мониторинг\Hujjatlar_Baza\... papkasiga yuklab jamlaydi.
"""

import os
import sys
import json
import time
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime

# Server URL (tashqi serverga yuklanganda shu manzil domen/IP ga o'zgartiriladi)
SERVER_URL = os.environ.get("MONITORING_SERVER_URL", "http://127.0.0.1:8080")
LOCAL_STORAGE_DIR = r"E:\мониторинг\Hujjatlar_Baza"
LOG_FILE = r"E:\мониторинг\sync_log.txt"

def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def get_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def run_sync():
    log(f"=== Sinxronizatsiya boshlandi (Server: {SERVER_URL}) ===")
    
    # 1. Fetch manifest
    manifest_url = f"{SERVER_URL}/api/sync/manifest"
    try:
        req = urllib.request.Request(manifest_url, headers={"User-Agent": "MMTB-AutoSyncAgent/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log(f"DIQQAT: Server bilan bog'lanib bo'lmadi ({e}). Server ishga tushganligini yoki internet aloqasini tekshiring.")
        return False

    if data.get("status") != "success":
        log(f"Xatolik: Server noto'g'ri javob berdi: {data}")
        return False

    files = data.get("files", [])
    latest_excel = data.get("latest_15_talik_excel")
    log(f"Serverda mavjud umumiy fayllar: {len(files)} ta.")

    downloaded_count = 0
    skipped_count = 0

    # 2. Sync Hujjatlar_Baza files
    for f_info in files:
        rel_path = f_info["rel_path"]
        remote_sha = f_info["sha256"]
        remote_size = f_info["size"]

        local_path = os.path.join(LOCAL_STORAGE_DIR, os.path.normpath(rel_path))
        
        # Check if local file exists and matches
        if os.path.exists(local_path):
            local_size = os.path.getsize(local_path)
            if local_size == remote_size:
                local_sha = get_file_sha256(local_path)
                if local_sha == remote_sha:
                    skipped_count += 1
                    continue

        # Download missing or updated file
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        download_url = f"{SERVER_URL}/api/sync/file?category=hujjatlar_baza&rel_path={urllib.parse.quote(rel_path)}"
        try:
            req = urllib.request.Request(download_url, headers={"User-Agent": "MMTB-AutoSyncAgent/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(local_path, "wb") as out_f:
                    out_f.write(resp.read())
            downloaded_count += 1
            log(f"Yuklab olindi: {rel_path} ({remote_size} bayt)")
        except Exception as e:
            log(f"Faylni yuklab olishda xatolik ({rel_path}): {e}")

    # 3. Sync latest 15-talik Excel
    if latest_excel:
        excel_rel = latest_excel["rel_path"]
        excel_local = os.path.join(LOCAL_STORAGE_DIR, os.path.normpath(excel_rel))
        remote_sha = latest_excel["sha256"]
        remote_size = latest_excel["size"]

        should_download_excel = True
        if os.path.exists(excel_local) and os.path.getsize(excel_local) == remote_size:
            if get_file_sha256(excel_local) == remote_sha:
                should_download_excel = False

        if should_download_excel:
            os.makedirs(os.path.dirname(excel_local), exist_ok=True)
            download_url = f"{SERVER_URL}/api/sync/file?category=15_talik_excel&rel_path={urllib.parse.quote(excel_rel)}"
            try:
                req = urllib.request.Request(download_url, headers={"User-Agent": "MMTB-AutoSyncAgent/1.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    with open(excel_local, "wb") as out_f:
                        out_f.write(resp.read())
                downloaded_count += 1
                log(f"15-talik Rasmiy Excel kitobi yangilandi: {excel_rel}")
            except Exception as e:
                log(f"15-talik Excelni yuklab olishda xatolik: {e}")

    log(f"=== Sinxronizatsiya yakunlandi: {downloaded_count} ta yangi fayl yuklandi, {skipped_count} ta o'zgarmagan fayl tasdiqlandi. ===")
    return True

if __name__ == "__main__":
    run_sync()
