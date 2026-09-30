# -*- coding: utf-8 -*-
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import os
import sys
import json
import shutil
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import get_db

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'static', 'uploads', 'exports')
os.makedirs(EXPORTS_DIR, exist_ok=True)

MONTH_NAMES_UZ = {
    1: 'Yanvar', 2: 'Fevral', 3: 'Mart', 4: 'Aprel',
    5: 'May', 6: 'Iyun', 7: 'Iyul', 8: 'Avgust',
    9: 'Sentyabr', 10: 'Oktyabr', 11: 'Noyabr', 12: 'Dekabr'
}

MONTH_NAMES_CYR = {
    1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
    5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
    9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
}

def generate_crime_analytical_word(month_num=8, year=2026):
    conn = get_db()
    cursor = conn.cursor()

    m_cyr = MONTH_NAMES_CYR.get(int(month_num), 'Август')
    m_uz = MONTH_NAMES_UZ.get(int(month_num), 'Avgust')

    # Query statistics from DB
    cursor.execute("""
    SELECT d.name as district_name, r.numeric_values 
    FROM monthly_15_records r
    JOIN monthly_15_submissions s ON r.submission_id = s.id
    JOIN districts d ON s.district_id = d.id
    WHERE r.direction_number = 10 AND s.year = ?
    ORDER BY d.sort_order
    """, (year,))
    rows = cursor.fetchall()

    doc = docx.Document()
    
    # Title
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = p_title.add_run(f"Фарғона вилояти Мактабгача ва мактаб таълими бошқармаси тизимидаги таълим муассасалари ўқувчилари томонидан содир этилган жиноятлар тўғрисида\nТАҲЛИЛИЙ МАЪЛУМОТНОМА ({year}-йил {m_cyr} ойи)")
    run_title.bold = True
    run_title.font.size = Pt(13)
    run_title.font.name = 'Times New Roman'

    # Summary text
    cursor.execute("SELECT COUNT(*) as total_cases FROM juvenile_incidents")
    total_cases = cursor.fetchone()['total_cases']

    p_intro = doc.add_paragraph()
    p_intro.paragraph_format.first_line_indent = Inches(0.5)
    r_intro = p_intro.add_run(f"Фарғона вилояти Ички ишлар бошқармаси ва бошқарма мониторинг бўлими маълумотига асосан, {year}-йил {m_cyr} ойи ҳолатига кўра, вилоятдаги 963 та таълим муассасаларида вояга етмаганлар билан олиб борилган профилактик ишлар ва содир этилган ҳуқуқбузарликлар таҳлил қилинди. Жами қайд этилган ҳолатлар сони: {total_cases} та.")
    r_intro.font.size = Pt(12)
    r_intro.font.name = 'Times New Roman'

    # Table
    table = doc.add_table(rows=1, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Table Grid'
    
    headers = ['Т/р', 'Ҳудуд номи', f'{year-1} йил ({month_num} ой)', f'{year} йил ({month_num} ой)', 'Фарқи (+/-)', 'Ҳолати']
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        hdr_cells[i].paragraphs[0].runs[0].bold = True
        hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    total_2025 = 0
    total_2026 = 0

    for idx, r in enumerate(rows, start=1):
        vals = json.loads(r['numeric_values'])
        j25 = vals.get('jinoyat_2025', 0)
        j26 = vals.get('jinoyat_2026', 0)
        diff = vals.get('farqi', j26 - j25)
        total_2025 += j25
        total_2026 += j26

        status_text = "Камайган" if diff < 0 else ("Ошган" if diff > 0 else "Тенг")
        
        row_cells = table.add_row().cells
        row_cells[0].text = str(idx)
        row_cells[1].text = r['district_name']
        row_cells[2].text = str(j25)
        row_cells[3].text = str(j26)
        row_cells[4].text = f"+{diff}" if diff > 0 else str(diff)
        row_cells[5].text = status_text

    # Total row
    tot_cells = table.add_row().cells
    tot_cells[0].text = ""
    tot_cells[1].text = "Вилоят бўйича жами:"
    tot_cells[1].paragraphs[0].runs[0].bold = True
    tot_cells[2].text = str(total_2025)
    tot_cells[2].paragraphs[0].runs[0].bold = True
    tot_cells[3].text = str(total_2026)
    tot_cells[3].paragraphs[0].runs[0].bold = True
    tot_cells[4].text = str(total_2026 - total_2025)
    tot_cells[4].paragraphs[0].runs[0].bold = True
    tot_cells[5].text = "Камайган" if (total_2026 - total_2025) < 0 else "Ошган"

    out_name = f"Tahliliy_Hisobot_{m_uz}_{year}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    out_path = os.path.join(EXPORTS_DIR, out_name)
    doc.save(out_path)
    conn.close()
    return out_name, out_path

def generate_15_talik_excel(month_num=8, year=2026):
    from app.services.monthly_15_service import export_updated_15_talik_workbook
    return export_updated_15_talik_workbook(month_num=month_num, year=year)

def generate_incidents_excel(month_num=8, year=2026):
    m_uz = MONTH_NAMES_UZ.get(int(month_num), 'Avgust')
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT i.case_number, i.district_name, i.school_name, i.student_fio, i.birth_date,
           i.criminal_article, i.home_address, a.school_responsible_fio, a.inspector_fio,
           a.current_study_status, i.status
    FROM juvenile_incidents i
    LEFT JOIN incident_actions a ON a.incident_id = i.id
    ORDER BY i.id ASC
    """)
    rows = cursor.fetchall()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Huquqbuzarliklar_{m_uz}"

    ws.append([f"Farg‘ona viloyati bo‘yicha voyaga yetmaganlar huquqbuzarliklari reyestri ({year}-yil {m_uz})"])
    ws.append(["№", "Tuman (shahar)", "Maktab/Sinf", "O‘quvchi F.I.Sh.", "Tug‘ilgan sana", "JK moddasi", "Yashash manzili", "Maktab mas’uli", "Profilaktika inspektori", "Hozirgi holat", "Status"])

    # Header style
    for col in range(1, 12):
        cell = ws.cell(2, col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="991B1B", end_color="991B1B", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r in rows:
        ws.append([
            r['case_number'],
            r['district_name'],
            r['school_name'],
            r['student_fio'],
            r['birth_date'] or '',
            r['criminal_article'] or '',
            r['home_address'] or '',
            r['school_responsible_fio'] or '',
            r['inspector_fio'] or '',
            r['current_study_status'] or '',
            r['status']
        ])

    out_name = f"Huquqbuzarliklar_Reyestri_{m_uz}_{year}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    out_path = os.path.join(EXPORTS_DIR, out_name)
    wb.save(out_path)
    conn.close()
    return out_name, out_path

def generate_discipline_rating(month_num=8, year=2026):
    m_uz = MONTH_NAMES_UZ.get(int(month_num), 'Avgust')
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT d.id, d.name as district_name,
           (SELECT COUNT(*) FROM task_district_assignments WHERE district_id = d.id) as total_tasks,
           (SELECT COUNT(*) FROM task_district_assignments WHERE district_id = d.id AND status = 'Tasdiqlandi') as done_tasks,
           (SELECT COUNT(*) FROM task_district_assignments WHERE district_id = d.id AND status = 'Kechikdi') as late_tasks,
           (SELECT COUNT(*) FROM juvenile_incidents WHERE district_id = d.id) as incidents
    FROM districts d
    ORDER BY d.sort_order
    """)
    rows = cursor.fetchall()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Ijro_Intizomi_{m_uz}"

    ws.append([f"Farg‘ona viloyati tuman va shaharlari bo‘yicha ijro intizomi reytingi ({year}-yil {m_uz})"])
    ws.append(["№", "Tuman / Shahar", "Jami topshiriqlar", "Bajarilgan", "Kechikkan", "Qayd etilgan jinoyatlar", "Ijro intizomi ko‘rsatkichi (%)", "Reyting darajasi"])

    for col in range(1, 9):
        cell = ws.cell(2, col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for idx, r in enumerate(rows, start=1):
        tot = r['total_tasks']
        done = r['done_tasks']
        late = r['late_tasks']
        pct = round((done / tot * 100), 1) if tot > 0 else 100.0
        
        rating = "Yashil (Yuqori)" if pct >= 90 else ("Sariq (O‘rta)" if pct >= 70 else "Qizil (Past)")

        ws.append([
            idx,
            r['district_name'],
            tot,
            done,
            late,
            r['incidents'],
            f"{pct}%",
            rating
        ])

    out_name = f"Ijro_Intizomi_Reytingi_{m_uz}_{year}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    out_path = os.path.join(EXPORTS_DIR, out_name)
    wb.save(out_path)
    conn.close()
    return out_name, out_path
