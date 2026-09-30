# -*- coding: utf-8 -*-
import os
import sys
import sqlite3
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Request, Response, HTTPException

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import get_db, log_audit

SESSION_COOKIE_NAME = "fargona_mmtb_session"

# Table for persistent sessions
def init_session_table():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)
    conn.commit()
    conn.close()

init_session_table()

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT u.id, u.username, u.password_hash, u.password_plain, u.fio, u.role, u.district_id, u.must_change_password,
           d.name as district_name, d.code as district_code, d.is_city
    FROM users u
    LEFT JOIN districts d ON u.district_id = d.id
    WHERE LOWER(u.username) = LOWER(?)
    """, (username.strip(),))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return None

    # Verify password against password_hash or password_plain
    is_valid = (user['password_hash'] == password) or (user['password_plain'] == password)
    if not is_valid:
        return None

    return {
        "id": user['id'],
        "username": user['username'],
        "fio": user['fio'],
        "role": user['role'],
        "district_id": user['district_id'],
        "district_name": user['district_name'],
        "district_code": user['district_code'],
        "is_city": user['is_city'],
        "must_change_password": bool(user['must_change_password'])
    }

def create_session(user_id: int, response: Response, days: int = 7) -> str:
    token = secrets.token_hex(32)
    expires_at = datetime.now() + timedelta(days=days)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO user_sessions (token, user_id, expires_at)
    VALUES (?, ?, ?)
    """, (token, user_id, expires_at.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=days * 24 * 3600,
        httponly=True,
        samesite="lax"
    )
    return token

def delete_session(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
    response.delete_cookie(SESSION_COOKIE_NAME)

def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT u.id, u.username, u.password_plain, u.fio, u.role, u.district_id, u.must_change_password,
           d.name as district_name, d.code as district_code, d.is_city,
           s.expires_at
    FROM user_sessions s
    JOIN users u ON s.user_id = u.id
    LEFT JOIN districts d ON u.district_id = d.id
    WHERE s.token = ?
    """, (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    # Check expiration
    try:
        exp = datetime.strptime(row['expires_at'], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > exp:
            return None
    except Exception:
        pass

    return {
        "id": row['id'],
        "username": row['username'],
        "fio": row['fio'],
        "role": row['role'],
        "district_id": row['district_id'],
        "district_name": row['district_name'],
        "district_code": row['district_code'],
        "is_city": row['is_city'],
        "must_change_password": bool(row['must_change_password'])
    }

def update_user_password(user_id: int, new_password: str) -> bool:
    if not new_password or len(new_password) < 3:
        return False

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE users 
    SET password_hash = ?, password_plain = ?, must_change_password = 0 
    WHERE id = ?
    """, (new_password, new_password, user_id))
    cursor.execute("SELECT username, fio, role, district_id FROM users WHERE id = ?", (user_id,))
    u = cursor.fetchone()
    conn.commit()
    conn.close()

    if u:
        log_audit("Parol Yangilandi", f"{u['fio']} ({u['username']}) shaxsiy parolini muvaffaqiyatli yangiladi.", user_fio=u['fio'], user_id=user_id)
    return True

def reset_district_password(user_id: int, admin_fio: str = "Administrator") -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE users 
    SET password_hash = '123', password_plain = '123', must_change_password = 1 
    WHERE id = ?
    """, (user_id,))
    cursor.execute("SELECT username, fio FROM users WHERE id = ?", (user_id,))
    u = cursor.fetchone()
    conn.commit()
    conn.close()

    if u:
        log_audit("Parol Tiklandi", f"{admin_fio} tomonidan {u['fio']} ({u['username']}) paroli '123' ga qaytarildi.")
    return True

def get_all_district_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT u.id, u.username, u.password_plain, u.fio, u.role, u.district_id, u.must_change_password,
           d.name as district_name, d.code as district_code, d.is_city,
           (SELECT COUNT(*) FROM task_district_assignments WHERE district_id = d.id) as task_count,
           (SELECT COUNT(*) FROM juvenile_incidents WHERE district_id = d.id) as incident_count
    FROM users u
    JOIN districts d ON u.district_id = d.id
    WHERE u.role = 'district'
    ORDER BY d.sort_order
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
