# -*- coding: utf-8 -*-
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'monitoring.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    # 1. Districts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS districts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        code TEXT,
        is_city INTEGER DEFAULT 0,
        sort_order INTEGER
    )
    """)

    # 2. Schools
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        district_id INTEGER NOT NULL,
        school_number TEXT,
        name TEXT NOT NULL,
        director_fio TEXT,
        director_phone TEXT,
        FOREIGN KEY (district_id) REFERENCES districts(id)
    )
    """)

    # 3. Users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        fio TEXT NOT NULL,
        role TEXT NOT NULL,
        district_id INTEGER,
        school_id INTEGER,
        telegram_chat_id TEXT,
        telegram_username TEXT,
        phone TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (district_id) REFERENCES districts(id),
        FOREIGN KEY (school_id) REFERENCES schools(id)
    )
    """)

    # 4. Work Plans
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS work_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        owner_fio TEXT NOT NULL,
        owner_role TEXT,
        year INTEGER DEFAULT 2026,
        title TEXT NOT NULL,
        source_filename TEXT,
        status TEXT DEFAULT 'Tasdiqlangan',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # 5. Work Plan Items
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS work_plan_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id INTEGER NOT NULL,
        section_number INTEGER,
        section_title TEXT,
        item_code TEXT,
        task_description TEXT NOT NULL,
        deadline_text TEXT,
        deadline_date TEXT,
        report_form TEXT,
        responsible_persons TEXT,
        target_type TEXT DEFAULT 'internal',
        target_district_id INTEGER,
        target_school_id INTEGER,
        status TEXT DEFAULT 'Kutilmoqda',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (plan_id) REFERENCES work_plans(id),
        FOREIGN KEY (target_district_id) REFERENCES districts(id),
        FOREIGN KEY (target_school_id) REFERENCES schools(id)
    )
    """)

    # 6. Task District Assignments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_district_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_plan_item_id INTEGER,
        district_id INTEGER NOT NULL,
        school_id INTEGER,
        assigned_by_user_id INTEGER,
        assignment_title TEXT,
        assignment_instructions TEXT,
        deadline_date TEXT,
        status TEXT DEFAULT 'Yangi',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (work_plan_item_id) REFERENCES work_plan_items(id),
        FOREIGN KEY (district_id) REFERENCES districts(id),
        FOREIGN KEY (school_id) REFERENCES schools(id),
        FOREIGN KEY (assigned_by_user_id) REFERENCES users(id)
    )
    """)

    # 7. Execution Proofs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS execution_proofs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_type TEXT NOT NULL,
        target_id INTEGER NOT NULL,
        submitted_by_user_id INTEGER,
        submitted_by_fio TEXT,
        proof_text TEXT,
        attachment_paths TEXT,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approval_status TEXT DEFAULT 'Kutilmoqda',
        approved_by_user_id INTEGER,
        rejection_reason TEXT
    )
    """)

    # 8. Monthly 15 Submissions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS monthly_15_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        district_id INTEGER NOT NULL,
        year INTEGER DEFAULT 2026,
        month INTEGER NOT NULL,
        submission_status TEXT DEFAULT 'Topshirildi',
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_locked INTEGER DEFAULT 0,
        FOREIGN KEY (district_id) REFERENCES districts(id)
    )
    """)

    # 9. Monthly 15 Records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS monthly_15_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER NOT NULL,
        direction_number INTEGER NOT NULL,
        direction_name TEXT,
        numeric_values TEXT,
        nominal_list TEXT,
        FOREIGN KEY (submission_id) REFERENCES monthly_15_submissions(id)
    )
    """)

    # 10. Juvenile Incidents
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS juvenile_incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_number INTEGER,
        district_id INTEGER,
        district_name TEXT,
        school_id INTEGER,
        school_name TEXT,
        student_fio TEXT NOT NULL,
        birth_date TEXT,
        gender TEXT,
        family_status TEXT,
        home_address TEXT,
        incident_details TEXT,
        criminal_article TEXT,
        incident_date TEXT,
        days_remaining INTEGER DEFAULT 10,
        status TEXT DEFAULT 'Nazoratda',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (district_id) REFERENCES districts(id),
        FOREIGN KEY (school_id) REFERENCES schools(id)
    )
    """)

    # 11. Incident Actions (10-day tracker)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS incident_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id INTEGER NOT NULL,
        school_responsible_fio TEXT,
        school_responsible_role TEXT,
        school_responsible_phone TEXT,
        mfy_responsible_fio TEXT,
        mfy_responsible_phone TEXT,
        inspector_fio TEXT,
        inspector_phone TEXT,
        current_study_status TEXT,
        assigned_pedagogue_fio TEXT,
        circle_name TEXT,
        circle_leader_fio TEXT,
        circle_leader_phone TEXT,
        report_file TEXT,
        is_completed_in_10_days INTEGER DEFAULT 0,
        completed_at TIMESTAMP,
        FOREIGN KEY (incident_id) REFERENCES juvenile_incidents(id)
    )
    """)

    # 12. Notifications
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        telegram_chat_id TEXT,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        type TEXT,
        is_sent INTEGER DEFAULT 0,
        sent_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 13. Audit Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        user_fio TEXT,
        action TEXT,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    districts_data = [
        ('Марғилон шаҳар', 'MRG', 1, 1),
        ('Фарғона шаҳар', 'FRG', 1, 2),
        ('Қувасой шаҳар', 'QVS', 1, 3),
        ('Қўқон шаҳар', 'QOQ', 1, 4),
        ('Бағдод тумани', 'BGD', 0, 5),
        ('Бешариқ тумани', 'BSH', 0, 6),
        ('Бувайда тумани', 'BVD', 0, 7),
        ('Данғара тумани', 'DNG', 0, 8),
        ('Ёзёвон тумани', 'YZV', 0, 9),
        ('Олтиариқ тумани', 'OLT', 0, 10),
        ('Қўштепа тумани', 'QSH', 0, 11),
        ('Риштон тумани', 'RSH', 0, 12),
        ('Сўх тумани', 'SOX', 0, 13),
        ('Тошлоқ тумани', 'TSH', 0, 14),
        ('Учкўприк тумани', 'UCH', 0, 15),
        ('Фарғона тумани', 'FRT', 0, 16),
        ('Фурқат тумани', 'FRQ', 0, 17),
        ('Ўзбекистон тумани', 'UZB', 0, 18),
        ('Қува тумани', 'QVA', 0, 19)
    ]

    for name, code, is_city, order in districts_data:
        cursor.execute("INSERT OR IGNORE INTO districts (name, code, is_city, sort_order) VALUES (?, ?, ?, ?)", (name, code, is_city, order))

    cursor.execute("INSERT OR IGNORE INTO users (id, username, password_hash, fio, role, phone) VALUES (1, 'admin', 'admin123', 'Bosh administrator', 'admin', '+998901234567')")
    cursor.execute("INSERT OR IGNORE INTO users (id, username, password_hash, fio, role, phone) VALUES (2, 'boshqarma_rahbar', 'rahbar123', 'Boshqarma boshlig‘i', 'regional_head', '+998911112233')")
    cursor.execute("INSERT OR IGNORE INTO users (id, username, password_hash, fio, role, phone) VALUES (3, 'azimov_a', 'azimov123', 'A.Azimov (Metodist-kurator)', 'curator', '+998933334455')")
    cursor.execute("INSERT OR IGNORE INTO users (id, username, password_hash, fio, role, phone) VALUES (4, 'turdiyev_r', 'turdiyev123', 'R.Turdiyev (Bo‘lim boshlig‘i)', 'curator', '+998944445566')")
    cursor.execute("INSERT OR IGNORE INTO users (id, username, password_hash, fio, role, phone) VALUES (5, 'azamov_d', 'azamov123', 'D.A’zamov (Mutaxassis)', 'curator', '+998955556677')")

    conn.commit()
    conn.close()

def log_audit(action: str, details: str, user_fio: str = "Bosh administrator", user_id: int = 1):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO audit_logs (user_id, user_fio, action, details) VALUES (?, ?, ?, ?)",
                       (user_id, user_fio, action, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Audit Log Error] {e}")

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
