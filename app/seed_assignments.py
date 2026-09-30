# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, r'e:\мониторинг\monitoring_platform')
from app.db import get_db

conn = get_db()
cursor = conn.cursor()

# Find items
cursor.execute("SELECT id, item_code, task_description FROM work_plan_items WHERE item_code IN ('2.1', '2.2', '3.2', '5.1')")
items = cursor.fetchall()

cursor.execute("SELECT id, name FROM districts WHERE name IN ('Марғилон шаҳар', 'Фарғона шаҳар', 'Қува тумани', 'Олтиариқ тумани')")
districts = cursor.fetchall()

for d in districts:
    for item in items:
        title = f"{item['item_code']}-band: {d['name']}da o‘rganish"
        cursor.execute("""
        INSERT INTO task_district_assignments (
            work_plan_item_id, district_id, assigned_by_user_id,
            assignment_title, assignment_instructions, deadline_date, status
        ) VALUES (?, ?, 3, ?, ?, '2026-10-15', 'Yangi')
        """, (item['id'], d['id'], title, item['task_description']))

conn.commit()
cursor.execute("SELECT COUNT(*) as cnt FROM task_district_assignments")
print("Total territorial task assignments:", cursor.fetchone()['cnt'])
conn.close()
