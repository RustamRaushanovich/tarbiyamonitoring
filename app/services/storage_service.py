# -*- coding: utf-8 -*-
import os
import re
import shutil
import subprocess
from datetime import datetime
from app.db import get_db

# Asosiy baza papkasi - foydalanuvchi kompyuterida
BASE_STORAGE_DIR = r"E:\мониторинг\Hujjatlar_Baza"

def sanitize_filename(name: str) -> str:
    """Windows tizimida papka va fayl nomlarida taqiqlangan belgilarni xavfsiz almashtirish"""
    if not name:
        return "Noma'lum"
    # Replace invalid chars: \ / : * ? " < > |
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:80]

def get_assignment_storage_path(assignment_id: int) -> dict:
    """Topshiriq ID bo'yicha kompyuterdagi ierarxik papka manzilini aniqlash va yaratish"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        a.id as assignment_id,
        a.assignment_title,
        a.assignment_instructions,
        a.deadline_date,
        d.name as district_name,
        wpi.id as item_id,
        wpi.item_code,
        wpi.task_description,
        wp.owner_fio,
        wp.year,
        wp.title as plan_title
    FROM task_district_assignments a
    JOIN districts d ON a.district_id = d.id
    LEFT JOIN work_plan_items wpi ON a.work_plan_item_id = wpi.id
    LEFT JOIN work_plans wp ON wpi.plan_id = wp.id
    WHERE a.id = ?
    """, (assignment_id,))
    
    info = cursor.fetchone()
    conn.close()

    if not info:
        # Fallback
        folder_path = os.path.join(BASE_STORAGE_DIR, "Umumiy_Hujjatlar", f"Topshiriq_{assignment_id}")
        os.makedirs(folder_path, exist_ok=True)
        return {
            "folder_path": folder_path,
            "district_name": "Noma'lum",
            "owner_fio": "Boshqarma",
            "item_code": "-",
            "assignment_title": f"Topshiriq #{assignment_id}"
        }

    owner = sanitize_filename(info['owner_fio'] or "Boshqarma")
    year = info['year'] or 2026
    item_code = sanitize_filename(info['item_code'] or f"Topshiriq_{assignment_id}")
    task_desc = sanitize_filename(info['task_description'] or info['assignment_title'] or "Tadbir")[:50]
    district = sanitize_filename(info['district_name'] or "Umumiy")

    # Masalan: E:\мониторинг\Hujjatlar_Baza\R_Turdiyev_2026\Band_1.3_Davomat\Beshariq_tumani\
    owner_folder = f"{owner}_{year}"
    band_folder = f"Band_{item_code}_{task_desc}"
    
    folder_path = os.path.join(BASE_STORAGE_DIR, owner_folder, band_folder, district)
    os.makedirs(folder_path, exist_ok=True)

    return {
        "folder_path": folder_path,
        "district_name": info['district_name'],
        "owner_fio": info['owner_fio'] or "Boshqarma",
        "item_code": info['item_code'] or "-",
        "assignment_title": info['assignment_title'] or "-",
        "deadline_date": info['deadline_date'] or "-",
        "task_description": info['task_description'] or info['assignment_title'] or "-"
    }

def save_uploaded_files_and_passport(assignment_id: int, submitted_by: str, proof_text: str, files: list) -> dict:
    """
    Fayllarni to'g'ridan-to'g'ri foydalanuvchi kompyuteridagi mos papkaga yuklab saqlaydi
    va avtomatik 'Hisobot_Pasporti.txt' ma'lumotnomasini yaratadi.
    """
    meta = get_assignment_storage_path(assignment_id)
    folder_path = meta["folder_path"]
    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    now_display = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    saved_files = []
    local_paths = []

    for file_obj in files:
        if not file_obj or not getattr(file_obj, "filename", None):
            continue
        
        orig_name = sanitize_filename(os.path.basename(file_obj.filename))
        dest_filename = f"{now_str}_{orig_name}"
        dest_full_path = os.path.join(folder_path, dest_filename)

        # Faylni diskka yozish
        with open(dest_full_path, "wb") as buffer:
            shutil.copyfileobj(file_obj.file, buffer)

        saved_files.append(dest_filename)
        local_paths.append(dest_full_path)

    # Avtomatik Hisobot Pasporti (.txt) yaratish
    passport_filename = f"Hisobot_Pasporti_{now_str}.txt"
    passport_path = os.path.join(folder_path, passport_filename)

    passport_content = f"""======================================================================
FARG‘ONA VILOYATI MAKTABGACHA VA MAKTAB TA’LIMI BOSHQARMASI
IJRO NAZORATI VA HISOBOTLARNI JAMLANMA PASPORTI
======================================================================
Topshiriq ID: #{assignment_id}
Topshiriq nomi: {meta['assignment_title']}
Ish rejasi bandi: {meta['item_code']} - {meta['task_description']}
Mas'ul kurator: {meta['owner_fio']}
Hudud (Tuman/Shahar): {meta['district_name']}
Topshiruvchi mas'ul: {submitted_by}
Topshirilgan vaqt: {now_display}
Belgilangan muddat: {meta['deadline_date']}

----------------------------------------------------------------------
BAJARILGAN ISH MAZMUNI VA IZOH:
----------------------------------------------------------------------
{proof_text}

----------------------------------------------------------------------
BIRIKTIRILGAN FAYLLAR ({len(saved_files)} ta):
----------------------------------------------------------------------
"""
    for idx, f in enumerate(saved_files, 1):
        passport_content += f"{idx}. {f}\n"

    passport_content += f"""
Saqlangan kompyuter papkasi:
{folder_path}
======================================================================
"""

    with open(passport_path, "w", encoding="utf-8") as pf:
        pf.write(passport_content)

    return {
        "folder_path": folder_path,
        "saved_files": saved_files,
        "local_paths": local_paths,
        "passport_path": passport_path
    }

def open_folder_in_windows_explorer(folder_path: str) -> bool:
    """Windows Explorer orqali papkani ochish"""
    try:
        if os.path.exists(folder_path):
            os.startfile(os.path.abspath(folder_path))
            return True
        else:
            # Agar papka hali yo'q bo'lsa, yaratib ochadi
            os.makedirs(folder_path, exist_ok=True)
            os.startfile(os.path.abspath(folder_path))
            return True
    except Exception as e:
        print(f"Error opening folder: {e}")
        return False
