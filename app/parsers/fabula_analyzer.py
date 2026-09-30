# -*- coding: utf-8 -*-
import os
import sys
import re
from datetime import datetime, date
import calendar

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import get_db

MONTHS_UZ = {
    'январ': 1, 'январь': 1, 'января': 1, 'yanvar': 1,
    'феврал': 2, 'февраль': 2, 'февраля': 2, 'fevral': 2,
    'март': 3, 'марта': 3, 'mart': 3,
    'апрел': 4, 'апрель': 4, 'апреля': 4, 'aprel': 4,
    'май': 5, 'мая': 5, 'may': 5,
    'июн': 6, 'июнь': 6, 'июня': 6, 'iyun': 6,
    'июл': 7, 'июль': 7, 'июля': 7, 'iyul': 7,
    'август': 8, 'августа': 8, 'avgust': 8,
    'сентябр': 9, 'сентябрь': 9, 'сентября': 9, 'sentabr': 9, 'sentyabr': 9,
    'октябр': 10, 'октябрь': 10, 'октября': 10, 'oktabr': 10, 'oktyabr': 10,
    'ноябр': 11, 'ноябрь': 11, 'ноября': 11, 'noyabr': 11,
    'декабр': 12, 'декабрь': 12, 'декабря': 12, 'dekabr': 12
}

WEEKDAYS_UZ = {
    0: 'Dushanba',
    1: 'Seshanba',
    2: 'Chorshanba',
    3: 'Payshanba',
    4: 'Juma',
    5: 'Shanba',
    6: 'Yakshanba'
}

def parse_incident_fabula(text: str, fallback_date_str: str = None) -> dict:
    """
    Parses crime fabula text to extract exact crime date, time, weekday, and determines
    whether it occurred during school hours: Monday to Saturday between 08:00 and 14:00.
    """
    if not text:
        text = ""

    parsed_year = None
    parsed_month = None
    parsed_day = None
    parsed_hour = None
    parsed_minute = 0

    # 1. Try to find date in text
    # Pattern: 17.01.2026 or 17/01/2026
    m_num_date = re.search(r'(\d{1,2})[\./](\d{1,2})[\./](\d{4})', text)
    if m_num_date:
        d, m, y = int(m_num_date.group(1)), int(m_num_date.group(2)), int(m_num_date.group(3))
        if 1 <= d <= 31 and 1 <= m <= 12 and 2020 <= y <= 2030:
            parsed_day, parsed_month, parsed_year = d, m, y

    # Pattern: 2026 йил(нинг) 06 январь (куни) or 06 январь 2026 йил
    if not parsed_day:
        m_cyr_date = re.search(
            r'(\d{4})\s*йил(?:нинг)?\s*(\d{1,2})\s*([а-яa-z]+)',
            text, re.IGNORECASE
        )
        if m_cyr_date:
            y = int(m_cyr_date.group(1))
            d = int(m_cyr_date.group(2))
            m_str = m_cyr_date.group(3).lower()
            for key, val in MONTHS_UZ.items():
                if m_str.startswith(key):
                    parsed_year, parsed_day, parsed_month = y, d, val
                    break

    # Pattern fallback: (\d{1,2}) ([а-яa-z]+) куни
    if not parsed_day:
        m_day_month = re.search(
            r'(\d{1,2})\s*([а-яa-z]+)\s*куни',
            text, re.IGNORECASE
        )
        if m_day_month:
            d = int(m_day_month.group(1))
            m_str = m_day_month.group(2).lower()
            for key, val in MONTHS_UZ.items():
                if m_str.startswith(key):
                    parsed_day, parsed_month = d, val
                    parsed_year = 2026
                    break

    # Fallback to database incident_date
    if not parsed_day and fallback_date_str:
        try:
            fb = datetime.strptime(fallback_date_str[:10], '%Y-%m-%d')
            parsed_year, parsed_month, parsed_day = fb.year, fb.month, fb.day
        except Exception:
            pass

    # 2. Extract Time
    # Pattern: соат 15:30 or соат 01:20 or soat 11.45
    m_time = re.search(r'(?:соат|soat|вақтида)\s*(\d{1,2})[:\.](\d{2})', text, re.IGNORECASE)
    if m_time:
        h = int(m_time.group(1))
        mn = int(m_time.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            parsed_hour = h
            parsed_minute = mn

    if parsed_hour is None:
        # Pattern: соат 13:00 ларда or соат 11 ларда
        m_approx = re.search(r'(?:соат|soat)\s*(\d{1,2})\s*(?:ларда|da|larda)?', text, re.IGNORECASE)
        if m_approx:
            h = int(m_approx.group(1))
            if 0 <= h <= 23:
                parsed_hour = h
                parsed_minute = 0

    if parsed_hour is None:
        # Pattern: кундузги / тунги
        if 'тунги' in text.lower() or 'кечқурун' in text.lower() or 'соат 2' in text.lower():
            parsed_hour = 21
            parsed_minute = 0

    # 3. Calculate Weekday
    weekday_idx = None
    weekday_name = "Noma'lum"
    if parsed_year and parsed_month and parsed_day:
        try:
            dt = date(parsed_year, parsed_month, parsed_day)
            weekday_idx = dt.weekday() # 0 = Monday, 6 = Sunday
            weekday_name = WEEKDAYS_UZ.get(weekday_idx, "Noma'lum")
        except Exception:
            pass

    # 4. Check School Hours condition:
    # Monday to Saturday (0 to 5) AND between 08:00 and 14:00 (08:00 <= time <= 14:00)
    is_school_time = 0
    badge = "⏳ Vaqti aniqlanmagan"
    exact_time_str = f"{parsed_hour:02d}:{parsed_minute:02d}" if parsed_hour is not None else ""

    if weekday_idx is not None and parsed_hour is not None:
        if weekday_idx == 6: # Sunday
            is_school_time = 0
            badge = "🏖 Dam olish kuni (Yakshanba)"
        elif 8 <= parsed_hour < 14 or (parsed_hour == 14 and parsed_minute == 0):
            is_school_time = 1
            badge = f"🚨 DARS VAQTIDA ({exact_time_str})"
        elif parsed_hour < 8:
            is_school_time = 0
            badge = f"🌅 Ertalabki (08:00 gacha, {exact_time_str})"
        else:
            is_school_time = 0
            badge = f"🌙 Darsdan keyin / Tungi ({exact_time_str})"
    elif parsed_hour is not None:
        if 8 <= parsed_hour < 14:
            is_school_time = 1
            badge = f"🚨 DARS VAQTIDA ({exact_time_str})"
        else:
            badge = f"🌙 Darsdan keyin ({exact_time_str})"

    return {
        'exact_time': exact_time_str,
        'weekday': weekday_name,
        'weekday_idx': weekday_idx,
        'is_school_time': is_school_time,
        'badge': badge,
        'date_iso': f"{parsed_year:04d}-{parsed_month:02d}-{parsed_day:02d}" if (parsed_year and parsed_month and parsed_day) else ""
    }

def update_all_incidents_school_time():
    """Batch processes all incidents in juvenile_incidents to populate school-time status."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, incident_details, incident_date FROM juvenile_incidents")
    rows = cursor.fetchall()

    school_time_count = 0
    non_school_count = 0

    for r in rows:
        analysis = parse_incident_fabula(r['incident_details'], r['incident_date'])
        cursor.execute("""
        UPDATE juvenile_incidents
        SET incident_exact_time = ?,
            incident_weekday = ?,
            is_school_time = ?,
            school_time_badge = ?
        WHERE id = ?
        """, (analysis['exact_time'], analysis['weekday'], analysis['is_school_time'], analysis['badge'], r['id']))

        if analysis['is_school_time'] == 1:
            school_time_count += 1
        else:
            non_school_count += 1

    conn.commit()
    conn.close()
    return {
        'total': len(rows),
        'school_time_count': school_time_count,
        'non_school_count': non_school_count
    }

if __name__ == '__main__':
    res = update_all_incidents_school_time()
    print("Fabula school-time batch processing complete:", res)
