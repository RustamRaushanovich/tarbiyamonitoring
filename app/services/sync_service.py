# -*- coding: utf-8 -*-
import os
import sys
import json
import hashlib
import zipfile
import io
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
BASE_STORAGE_DIR = r"E:\мониторинг\Hujjatlar_Baza"
EXPORTS_DIR = os.path.join(PROJECT_ROOT, "exports")
DB_PATH = os.path.join(PROJECT_ROOT, "data", "monitoring.db")

def get_file_sha256(filepath: str) -> str:
    """Calculates SHA256 hash of a file for integrity check."""
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def get_sync_manifest() -> dict:
    """
    Generates a full manifest of all files stored in Hujjatlar_Baza
    and the latest 15-talik Excel exports.
    """
    files = []
    
    # 1. Scan Hujjatlar_Baza
    if os.path.exists(BASE_STORAGE_DIR):
        for root, dirs, filenames in os.walk(BASE_STORAGE_DIR):
            for fname in filenames:
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, BASE_STORAGE_DIR).replace("\\", "/")
                
                try:
                    stat = os.stat(full_path)
                    files.append({
                        "category": "hujjatlar_baza",
                        "rel_path": rel_path,
                        "filename": fname,
                        "size": stat.st_size,
                        "mtime": int(stat.st_mtime),
                        "sha256": get_file_sha256(full_path)
                    })
                except Exception:
                    continue

    # 2. Find latest 15-talik Excel
    latest_excel = None
    if os.path.exists(EXPORTS_DIR):
        excel_files = [f for f in os.listdir(EXPORTS_DIR) if f.endswith(".xlsx") and "15_Talik" in f]
        if excel_files:
            excel_files.sort(key=lambda x: os.path.getmtime(os.path.join(EXPORTS_DIR, x)), reverse=True)
            newest = excel_files[0]
            newest_full = os.path.join(EXPORTS_DIR, newest)
            stat = os.stat(newest_full)
            latest_excel = {
                "category": "15_talik_excel",
                "rel_path": f"15_Talik_Monitoring/{newest}",
                "filename": newest,
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
                "sha256": get_file_sha256(newest_full)
            }

    # 3. Database info
    db_info = None
    if os.path.exists(DB_PATH):
        db_stat = os.stat(DB_PATH)
        db_info = {
            "size": db_stat.st_size,
            "mtime": int(db_stat.st_mtime)
        }

    return {
        "status": "success",
        "server_time": datetime.now().isoformat(),
        "total_files": len(files),
        "files": files,
        "latest_15_talik_excel": latest_excel,
        "database": db_info
    }

def resolve_sync_file_path(category: str, rel_path: str):
    """
    Safely resolves a file path to prevent directory traversal.
    """
    clean_rel = os.path.normpath(rel_path).replace("\\", "/")
    if ".." in clean_rel or clean_rel.startswith("/"):
        return None

    if category == "15_talik_excel":
        fname = os.path.basename(clean_rel)
        full_path = os.path.join(EXPORTS_DIR, fname)
        if os.path.exists(full_path):
            return full_path
        # Check permanent backup
        alt_path = os.path.join(BASE_STORAGE_DIR, clean_rel)
        if os.path.exists(alt_path):
            return alt_path
    else:
        full_path = os.path.join(BASE_STORAGE_DIR, clean_rel)
        if os.path.exists(full_path):
            return full_path

    return None

def create_full_sync_archive() -> tuple:
    """
    Packages all Hujjatlar_Baza files and the latest 15-talik Excel
    into a single ZIP archive for instant offline sync.
    """
    zip_buffer = io.BytesIO()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"MMTB_Monitoring_Baza_{timestamp}.zip"

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        if os.path.exists(BASE_STORAGE_DIR):
            for root, dirs, files in os.walk(BASE_STORAGE_DIR):
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, BASE_STORAGE_DIR)
                    zipf.write(full_p, arcname=f"Hujjatlar_Baza/{rel_p}")

        # Also write latest Excel export
        if os.path.exists(EXPORTS_DIR):
            excel_files = [f for f in os.listdir(EXPORTS_DIR) if f.endswith(".xlsx") and "15_Talik" in f]
            if excel_files:
                excel_files.sort(key=lambda x: os.path.getmtime(os.path.join(EXPORTS_DIR, x)), reverse=True)
                newest = os.path.join(EXPORTS_DIR, excel_files[0])
                zipf.write(newest, arcname=f"15_Talik_Rasmiy_Kitob/{excel_files[0]}")

    zip_buffer.seek(0)
    return zip_filename, zip_buffer.getvalue()
