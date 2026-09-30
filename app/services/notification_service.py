# -*- coding: utf-8 -*-
import os
import sys
from datetime import datetime, date, timedelta

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import get_db
import requests

def _load_env_file():
    env_path = os.path.join(PROJECT_ROOT, '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass

_load_env_file()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")

def send_telegram_message(chat_id: str, text: str, parse_mode: str = "HTML") -> dict:
    """Sends a notification message via Telegram Bot API."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    if not token or not chat_id:
        return {"status": "error", "message": "Telegram Bot Token yoki Chat ID ko‘rsatilmagan"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        data = res.json()
        if data.get("ok"):
            return {"status": "success", "result": data.get("result")}
        else:
            return {"status": "error", "message": data.get("description", "Noma’lum xatolik")}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def run_deadline_checks():
    conn = get_db()
    cursor = conn.cursor()
    today = date.today()

    generated_alerts = []

    # 1. Check Task District Assignments
    cursor.execute("""
    SELECT a.id, a.assignment_title, a.deadline_date, a.status, d.name as district_name, u.telegram_chat_id, u.fio
    FROM task_district_assignments a
    JOIN districts d ON a.district_id = d.id
    LEFT JOIN users u ON u.district_id = d.id
    WHERE a.status NOT IN ('Tasdiqlandi', 'Yakunlandi')
    """)
    tasks = cursor.fetchall()

    for t in tasks:
        d_str = t['deadline_date']
        if not d_str:
            continue
        try:
            d_date = datetime.strptime(d_str[:10], '%Y-%m-%d').date()
            diff_days = (d_date - today).days

            alert_type = None
            msg = None

            if diff_days == 5:
                alert_type = 'alert_5_days'
                msg = f"⏳ 5 KUN QOLDI: '{t['assignment_title']}' ijro muddati 5 kundan so‘ng tugaydi ({d_str})."
            elif diff_days == 3:
                alert_type = 'alert_3_days'
                msg = f"⚠️ 3 KUN QOLDI: '{t['assignment_title']}' topshirig‘i bo‘yicha hisobot tayyorlang ({d_str})."
            elif diff_days == 1:
                alert_type = 'alert_1_day'
                msg = f"🚨 1 KUN QOLDI! '{t['assignment_title']}' ertaga muddati tugaydi!"
            elif diff_days < 0:
                alert_type = 'overdue'
                msg = f"❌ MUDDATI O‘TDI: '{t['assignment_title']}' {abs(diff_days)} kunga kechikmoqda!"
                cursor.execute("UPDATE task_district_assignments SET status = 'Kechikdi' WHERE id = ?", (t['id'],))

            if alert_type:
                cursor.execute("""
                INSERT INTO notifications (telegram_chat_id, title, message, type)
                VALUES (?, ?, ?, ?)
                """, (t['telegram_chat_id'], f"Ijro nazorati: {t['district_name']}", msg, alert_type))
                generated_alerts.append(msg)
        except Exception as e:
            continue

    # 2. Check Juvenile Incidents 10-day countdown
    cursor.execute("""
    SELECT i.id, i.student_fio, i.school_name, i.district_name, i.created_at, a.is_completed_in_10_days
    FROM juvenile_incidents i
    LEFT JOIN incident_actions a ON a.incident_id = i.id
    WHERE i.status = 'Nazoratda' AND (a.is_completed_in_10_days = 0 OR a.is_completed_in_10_days IS NULL)
    """)
    incidents = cursor.fetchall()

    for inc in incidents:
        # Calculate remaining days
        try:
            c_date = datetime.strptime(inc['created_at'][:10], '%Y-%m-%d').date()
            elapsed = (today - c_date).days
            remaining = max(0, 10 - elapsed)
            cursor.execute("UPDATE juvenile_incidents SET days_remaining = ? WHERE id = ?", (remaining, inc['id']))
            if remaining <= 2:
                msg = f"🚨 DIQQAT: {inc['district_name']} {inc['school_name']} o‘quvchisi {inc['student_fio']} bo‘yicha 10 kunlik nazorat muddatiga {remaining} kun qoldi!"
                cursor.execute("""
                INSERT INTO notifications (title, message, type)
                VALUES (?, ?, 'incident_10_days')
                """, (f"10-kunlik muddat nazorati: {inc['district_name']}", msg))
                generated_alerts.append(msg)
        except Exception:
            continue

    conn.commit()
    conn.close()
    return generated_alerts

def broadcast_deadline_alerts_to_telegram(target_chat_id: str = None) -> dict:
    """Runs deadline checks and sends a structured digest to the admin or specified chat via Telegram."""
    chat_id = target_chat_id or os.getenv("TELEGRAM_ADMIN_CHAT_ID", TELEGRAM_ADMIN_CHAT_ID)
    alerts = run_deadline_checks()
    if not alerts:
        msg = "✅ <b>Farg‘ona MMTB Ijro Nazorati:</b>\n\nBugungi kunda muddati o‘tgan yoki shoshilinch (3 kundan kam qolgan) topshiriqlar mavjud emas."
        if chat_id:
            send_telegram_message(chat_id, msg)
        return {"status": "success", "sent": bool(chat_id), "count": 0, "alerts": []}

    urgent_count = len(alerts)
    header = f"🚨 <b>FARG‘ONA MMTB IJRO NAZORATI VA PROFILAKTIKA OGOHLANTIRIShI</b>\n"
    header += f"<i>Sana: {datetime.now().strftime('%d.%m.%Y %H:%M')}</i>\n\n"
    header += f"Jami <b>{urgent_count} ta</b> shoshilinch yoki kechikkan holat aniqlandi:\n\n"

    body = ""
    for i, a in enumerate(alerts[:8], start=1):
        body += f"<b>{i}.</b> {a}\n\n"
    if len(alerts) > 8:
        body += f"<i>...va yana {len(alerts) - 8} ta topshiriq platformada ko‘rsatilgan.</i>\n\n"
    footer = "🌐 Platformaga kirish: http://localhost:8080"

    full_text = header + body + footer
    send_res = {"status": "skipped", "message": "Chat ID ko'rsatilmagan"}
    if chat_id:
        send_res = send_telegram_message(chat_id, full_text)

    return {
        "status": "success",
        "alerts_count": urgent_count,
        "alerts": alerts,
        "telegram_delivery": send_res
    }

if __name__ == '__main__':
    alerts = run_deadline_checks()
    print(f"Deadline checks finished. {len(alerts)} alerts generated.")
