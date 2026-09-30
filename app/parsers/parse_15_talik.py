# -*- coding: utf-8 -*-
import openpyxl
import os
import json
from app.db import get_db

def parse_and_import_15_talik(filepath=r'e:\мониторинг\Фарғона_вилояти_15_талик_2026_йил_8_ойи_2_1.xlsx', year=2026, month=8):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False

    wb = openpyxl.load_workbook(filepath, data_only=True)
    conn = get_db()
    cursor = conn.cursor()

    # Get districts map
    cursor.execute("SELECT id, name FROM districts")
    districts = cursor.fetchall()
    districts_map = {d['name'].lower(): d['id'] for d in districts}

    # Ensure monthly submission exists for each district
    submission_ids = {}
    for d in districts:
        cursor.execute("""
        INSERT OR IGNORE INTO monthly_15_submissions (district_id, year, month, submission_status, is_locked)
        VALUES (?, ?, ?, 'Topshirildi', 1)
        """, (d['id'], year, month))
        cursor.execute("SELECT id FROM monthly_15_submissions WHERE district_id = ? AND year = ? AND month = ?", (d['id'], year, month))
        sub = cursor.fetchone()
        if sub:
            submission_ids[d['id']] = sub['id']

    # 1. Parse Sheet 1: 1-Нотинч
    if '1-Нотинч' in wb.sheetnames:
        s1 = wb['1-Нотинч']
        for r in range(6, 26):
            tuman_val = s1.cell(r, 2).value
            if not tuman_val: continue
            tuman_name = str(tuman_val).strip()
            did = None
            for dname, d_id in districts_map.items():
                if dname.replace('шаҳар','').replace('тумани','').strip() in tuman_name.lower():
                    did = d_id
                    break
            if did and did in submission_ids:
                sub_id = submission_ids[did]
                data = {
                    'jami_oilalar': s1.cell(r, 3).value or 0,
                    'farzandlar': s1.cell(r, 4).value or 0,
                    'qizlar': s1.cell(r, 5).value or 0,
                    'noqobil': s1.cell(r, 6).value or 0,
                    'notinch': s1.cell(r, 7).value or 0,
                    'kam_taminlangan': s1.cell(r, 8).value or 0
                }
                cursor.execute("""
                INSERT INTO monthly_15_records (submission_id, direction_number, direction_name, numeric_values)
                VALUES (?, 1, 'Нотинч ва ноқобил оилалар', ?)
                """, (sub_id, json.dumps(data, ensure_ascii=False)))

    # 2. Parse Sheet 10: 10-жиноят сони
    if '10-жиноят сони' in wb.sheetnames:
        s10 = wb['10-жиноят сони']
        for r in range(7, 26):
            tuman_val = s10.cell(r, 3).value
            if not tuman_val: continue
            tuman_name = str(tuman_val).strip()
            did = None
            for dname, d_id in districts_map.items():
                if dname.replace('шаҳар','').replace('тумани','').strip() in tuman_name.lower():
                    did = d_id
                    break
            if did and did in submission_ids:
                sub_id = submission_ids[did]
                data = {
                    'jinoyat_2025': s10.cell(r, 4).value or 0,
                    'ishtirokchi_2025': s10.cell(r, 5).value or 0,
                    'jinoyat_2026': s10.cell(r, 6).value or 0,
                    'ishtirokchi_2026': s10.cell(r, 7).value or 0,
                    'farqi': s10.cell(r, 8).value or 0
                }
                cursor.execute("""
                INSERT INTO monthly_15_records (submission_id, direction_number, direction_name, numeric_values)
                VALUES (?, 10, 'Жиноятчилик сони ва динамикаси', ?)
                """, (sub_id, json.dumps(data, ensure_ascii=False)))

    # 3. Parse Sheet 6: 6-эрта туғруқ
    if '6-эрта туғруқ' in wb.sheetnames:
        s6 = wb['6-эрта туғруқ']
        for r in range(6, 26):
            tuman_val = s6.cell(r, 2).value or s6.cell(r, 3).value
            if not tuman_val: continue
            tuman_name = str(tuman_val).strip()
            did = None
            for dname, d_id in districts_map.items():
                if dname.replace('шаҳар','').replace('тумани','').strip() in tuman_name.lower():
                    did = d_id
                    break
            if did and did in submission_ids:
                sub_id = submission_ids[did]
                vals = [s6.cell(r, c).value or 0 for c in range(3, 10)]
                cursor.execute("""
                INSERT INTO monthly_15_records (submission_id, direction_number, direction_name, numeric_values)
                VALUES (?, 6, 'Эрта никоҳ ва эрта туғруқ', ?)
                """, (sub_id, json.dumps({'values': vals}, ensure_ascii=False)))

    # 4. Parse Sheet 8: 8-Ўз жонига қасд
    if '8-Ўз жонига қасд' in wb.sheetnames:
        s8 = wb['8-Ўз жонига қасд']
        for r in range(6, 26):
            tuman_val = s8.cell(r, 2).value or s8.cell(r, 3).value
            if not tuman_val: continue
            tuman_name = str(tuman_val).strip()
            did = None
            for dname, d_id in districts_map.items():
                if dname.replace('шаҳар','').replace('тумани','').strip() in tuman_name.lower():
                    did = d_id
                    break
            if did and did in submission_ids:
                sub_id = submission_ids[did]
                vals = [s8.cell(r, c).value or 0 for c in range(3, 10)]
                cursor.execute("""
                INSERT INTO monthly_15_records (submission_id, direction_number, direction_name, numeric_values)
                VALUES (?, 8, 'Ўз жонига қасд ва суицид', ?)
                """, (sub_id, json.dumps({'values': vals}, ensure_ascii=False)))

    # 5. Parse Sheet 12: 12-Чет элга кетган
    if '12-Чет элга кетган ' in wb.sheetnames:
        s12 = wb['12-Чет элга кетган ']
        for r in range(6, 26):
            tuman_val = s12.cell(r, 2).value or s12.cell(r, 3).value
            if not tuman_val: continue
            tuman_name = str(tuman_val).strip()
            did = None
            for dname, d_id in districts_map.items():
                if dname.replace('шаҳар','').replace('тумани','').strip() in tuman_name.lower():
                    did = d_id
                    break
            if did and did in submission_ids:
                sub_id = submission_ids[did]
                vals = [s12.cell(r, c).value or 0 for c in range(3, 10)]
                cursor.execute("""
                INSERT INTO monthly_15_records (submission_id, direction_number, direction_name, numeric_values)
                VALUES (?, 12, 'Чет элга чиқиб кетган ўқувчилар', ?)
                """, (sub_id, json.dumps({'values': vals}, ensure_ascii=False)))

    # 6. Parse Sheet 14: 14 Сурункали дарс колдирилган
    if '14 Сурункали дарс колдирилган' in wb.sheetnames:
        s14 = wb['14 Сурункали дарс колдирилган']
        for r in range(6, 26):
            tuman_val = s14.cell(r, 2).value or s14.cell(r, 3).value
            if not tuman_val: continue
            tuman_name = str(tuman_val).strip()
            did = None
            for dname, d_id in districts_map.items():
                if dname.replace('шаҳар','').replace('тумани','').strip() in tuman_name.lower():
                    did = d_id
                    break
            if did and did in submission_ids:
                sub_id = submission_ids[did]
                vals = [s14.cell(r, c).value or 0 for c in range(3, 10)]
                cursor.execute("""
                INSERT INTO monthly_15_records (submission_id, direction_number, direction_name, numeric_values)
                VALUES (?, 14, 'Сурункали дарс қолдирганлар', ?)
                """, (sub_id, json.dumps({'values': vals}, ensure_ascii=False)))

    conn.commit()
    conn.close()
    print("15-talik monitoring data imported successfully for 19 districts.")
    return True

if __name__ == '__main__':
    parse_and_import_15_talik()
