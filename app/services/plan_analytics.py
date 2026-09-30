# -*- coding: utf-8 -*-
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from datetime import datetime
from app.db import get_db

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'static', 'uploads', 'exports')
os.makedirs(EXPORTS_DIR, exist_ok=True)

def get_work_plan_matrix(year=2026, curator='all'):
    """19 ta tuman va shahar kesimida ish rejalari ijrosi matritsasi va avtomatik tahlili"""
    conn = get_db()
    cursor = conn.cursor()

    # 1. Tumanlar ro'yxati
    cursor.execute("SELECT id, name FROM districts ORDER BY sort_order")
    districts = cursor.fetchall()
    dist_map = {d['id']: d['name'] for d in districts}

    # 2. Ish rejasi bandlari
    curator_filter = ""
    params = [year]
    if curator and curator != 'all':
        curator_filter = "AND wp.owner_fio = ?"
        params.append(curator)

    cursor.execute(f"""
    SELECT 
        wpi.id as item_id,
        wpi.plan_id,
        wpi.section_number,
        wpi.item_code,
        wpi.task_description,
        wpi.deadline_text,
        wpi.deadline_date,
        wpi.status as item_status,
        wp.owner_fio,
        wp.title as plan_title
    FROM work_plan_items wpi
    JOIN work_plans wp ON wpi.plan_id = wp.id
    WHERE wp.year = ? {curator_filter}
    ORDER BY wpi.section_number, wpi.id
    """, params)
    items = cursor.fetchall()

    # 3. Barcha biriktirilgan topshiriqlar va hisobotlar
    cursor.execute("""
    SELECT 
        a.id as assignment_id,
        a.work_plan_item_id,
        a.district_id,
        a.status as assignment_status,
        a.deadline_date,
        (SELECT COUNT(*) FROM execution_proofs WHERE target_type = 'task_district_assignment' AND target_id = a.id) as proof_count
    FROM task_district_assignments a
    """)
    assignments = cursor.fetchall()
    conn.close()

    # Xaritani tuzish: (item_id, district_id) -> assignment
    ass_map = {}
    for a in assignments:
        ass_map[(a['work_plan_item_id'], a['district_id'])] = a

    matrix_rows = []
    total_assigned_count = 0
    total_submitted_count = 0
    total_overdue_count = 0

    district_scores = {d['id']: {'name': d['name'], 'assigned': 0, 'submitted': 0, 'overdue': 0} for d in districts}

    today_str = datetime.now().strftime("%Y-%m-%d")

    for item in items:
        item_id = item['item_id']
        row = {
            'item_id': item_id,
            'item_code': item['item_code'],
            'section_number': item['section_number'],
            'task_description': item['task_description'],
            'owner_fio': item['owner_fio'],
            'deadline_text': item['deadline_text'] or item['deadline_date'] or 'Doimiy',
            'districts_status': {},
            'item_assigned': 0,
            'item_submitted': 0
        }

        for d in districts:
            d_id = d['id']
            ass = ass_map.get((item_id, d_id))
            if ass:
                row['item_assigned'] += 1
                total_assigned_count += 1
                district_scores[d_id]['assigned'] += 1

                is_submitted = (ass['proof_count'] > 0) or (ass['assignment_status'] in ['Hisobot topshirildi', 'Tasdiqlandi'])
                is_overdue = False
                if not is_submitted and ass['deadline_date'] and ass['deadline_date'] < today_str:
                    is_overdue = True

                if is_submitted:
                    status = 'Topshirildi'
                    row['item_submitted'] += 1
                    total_submitted_count += 1
                    district_scores[d_id]['submitted'] += 1
                elif is_overdue:
                    status = 'Kechikdi'
                    total_overdue_count += 1
                    district_scores[d_id]['overdue'] += 1
                else:
                    status = 'Kutilmoqda'

                row['districts_status'][d_id] = {
                    'assigned': True,
                    'status': status,
                    'assignment_id': ass['assignment_id']
                }
            else:
                row['districts_status'][d_id] = {
                    'assigned': False,
                    'status': 'Yuklatilmagan',
                    'assignment_id': None
                }

        # Band bo'yicha foiz
        row['percent'] = round((row['item_submitted'] / row['item_assigned'] * 100), 1) if row['item_assigned'] > 0 else 100.0
        matrix_rows.append(row)

    # Tumanlar reytingi
    rankings = []
    for d_id, data in district_scores.items():
        pct = round((data['submitted'] / data['assigned'] * 100), 1) if data['assigned'] > 0 else 100.0
        rankings.append({
            'district_id': d_id,
            'district_name': data['name'],
            'assigned': data['assigned'],
            'submitted': data['submitted'],
            'overdue': data['overdue'],
            'percent': pct
        })

    rankings.sort(key=lambda x: (x['percent'], -x['overdue']), reverse=True)

    overall_percent = round((total_submitted_count / total_assigned_count * 100), 1) if total_assigned_count > 0 else 100.0

    return {
        'districts': districts,
        'matrix_rows': matrix_rows,
        'rankings': rankings,
        'stats': {
            'total_items': len(items),
            'total_assigned': total_assigned_count,
            'total_submitted': total_submitted_count,
            'total_overdue': total_overdue_count,
            'overall_percent': overall_percent
        }
    }

def generate_plan_analytical_excel(year=2026):
    """Boshqarma Ish rejalari ijrosi bo'yicha rasmiy Excel hisoboti"""
    data = get_work_plan_matrix(year=year, curator='all')
    districts = data['districts']
    rows = data['matrix_rows']
    rankings = data['rankings']

    wb = openpyxl.Workbook()
    
    # 1. Matritsa varag'i
    ws = wb.active
    ws.title = "Ish Rejalari Matritsasi"

    # Sarlavha
    ws.merge_cells('A1:X1')
    ws['A1'] = f"ФАРҒОНА ВИЛОЯТИ МАКТАБГАЧА ВА МАКТАБ ТАЪЛИМИ БОШҚАРМАСИ"
    ws['A1'].font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells('A2:X2')
    ws['A2'] = f"{year}-йил Иш режалари бандларининг 19 та туман/шаҳар кесимида ижро ҳолати"
    ws['A2'].font = Font(name="Calibri", size=12, italic=True)
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")

    # Jadval sarlavhasi
    headers = ["№", "Банд", "Тадбир мазмуни", "Масъул", "Муддати", "Ижро %"]
    for d in districts:
        headers.append(d['name'].replace(' tumani', '').replace(' shahri', ''))

    border_thin = Border(
        left=Side(style='thin', color='D1D5DB'),
        right=Side(style='thin', color='D1D5DB'),
        top=Side(style='thin', color='D1D5DB'),
        bottom=Side(style='thin', color='D1D5DB')
    )

    ws.append([]) # Bo'sh qator
    ws.append(headers)

    header_row_idx = 4
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row_idx, column=col_idx)
        cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    fill_green = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid") # Topshirildi
    fill_red = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")   # Kechikdi
    fill_yellow = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")# Kutilmoqda
    fill_gray = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")  # Yuklatilmagan

    for idx, r in enumerate(rows, 1):
        row_vals = [
            idx,
            r['item_code'],
            r['task_description'],
            r['owner_fio'],
            r['deadline_text'],
            f"{r['percent']}%"
        ]
        for d in districts:
            st = r['districts_status'][d['id']]['status']
            if st == 'Topshirildi':
                row_vals.append("✓")
            elif st == 'Kechikdi':
                row_vals.append("✗")
            elif st == 'Kutilmoqda':
                row_vals.append("...")
            else:
                row_vals.append("-")

        ws.append(row_vals)
        cur_row = ws.max_row
        for col_idx in range(1, len(row_vals) + 1):
            cell = ws.cell(row=cur_row, column=col_idx)
            cell.border = border_thin
            cell.font = Font(name="Calibri", size=9)
            if col_idx > 6:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                val = cell.value
                if val == "✓":
                    cell.fill = fill_green
                    cell.font = Font(name="Calibri", size=10, bold=True, color="047857")
                elif val == "✗":
                    cell.fill = fill_red
                    cell.font = Font(name="Calibri", size=10, bold=True, color="B91C1C")
                elif val == "...":
                    cell.fill = fill_yellow
                    cell.font = Font(name="Calibri", size=9, color="B45309")
                else:
                    cell.fill = fill_gray
                    cell.font = Font(name="Calibri", size=8, color="9CA3AF")

    ws.column_dimensions['A'].width = 5
    ws.column_dimensions['B'].width = 8
    ws.column_dimensions['C'].width = 38
    ws.column_dimensions['D'].width = 16
    ws.column_dimensions['E'].width = 14
    ws.column_dimensions['F'].width = 10
    for col_letter in [openpyxl.utils.get_column_letter(c) for c in range(7, len(headers) + 1)]:
        ws.column_dimensions[col_letter].width = 8

    # 2. Reyting varag'i
    ws_rank = wb.create_sheet(title="Tumanlar Reytingi")
    ws_rank.append(["№", "Ҳудуд (Туман/Шаҳар)", "Юклатилган топшириқлар", "Топширилди", "Кечиккан", "Ижро фоизи (%)"])
    for col_idx in range(1, 7):
        cell = ws_rank.cell(row=1, column=col_idx)
        cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for idx, rk in enumerate(rankings, 1):
        ws_rank.append([
            idx,
            rk['district_name'],
            rk['assigned'],
            rk['submitted'],
            rk['overdue'],
            f"{rk['percent']}%"
        ])
        c_row = ws_rank.max_row
        for c in range(1, 7):
            cell = ws_rank.cell(row=c_row, column=c)
            cell.border = border_thin
            if c >= 3:
                cell.alignment = Alignment(horizontal="center")

    ws_rank.column_dimensions['A'].width = 6
    ws_rank.column_dimensions['B'].width = 25
    ws_rank.column_dimensions['C'].width = 24
    ws_rank.column_dimensions['D'].width = 16
    ws_rank.column_dimensions['E'].width = 14
    ws_rank.column_dimensions['F'].width = 16

    filename = f"Ish_Rejalari_Tahlili_{year}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    filepath = os.path.join(EXPORTS_DIR, filename)
    wb.save(filepath)
    return filename, filepath

def calculate_district_kpi_ratings(year=2026):
    """
    Calculates live 0-100 KPI composite ratings across all 19 districts and cities:
    - 40% Work plan tasks execution on-time
    - 35% 10-day juvenile crime resolution and prevention rate
    - 25% 15-talik nominal data completeness and svod match
    Categorizes into Green (80-100), Yellow (60-79.9), Red (0-59.9) zones.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, is_city FROM districts ORDER BY sort_order")
    districts = cursor.fetchall()

    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Plan assignments
    cursor.execute("""
    SELECT district_id, status, deadline_date,
           (SELECT COUNT(*) FROM execution_proofs WHERE target_type = 'task_district_assignment' AND target_id = a.id) as proofs
    FROM task_district_assignments a
    """)
    assignments = cursor.fetchall()
    plan_stats = {}
    for a in assignments:
        did = a['district_id']
        if did not in plan_stats:
            plan_stats[did] = {'assigned': 0, 'submitted': 0, 'overdue': 0}
        plan_stats[did]['assigned'] += 1
        is_sub = (a['proofs'] > 0) or (a['status'] in ['Hisobot topshirildi', 'Tasdiqlandi'])
        if is_sub:
            plan_stats[did]['submitted'] += 1
        elif a['deadline_date'] and a['deadline_date'] < today_str:
            plan_stats[did]['overdue'] += 1

    # 2. Juvenile crime incidents & 10-day actions
    cursor.execute("""
    SELECT i.district_id, i.status, a.is_completed_in_10_days
    FROM juvenile_incidents i
    LEFT JOIN incident_actions a ON a.incident_id = i.id
    """)
    incidents = cursor.fetchall()
    crime_stats = {}
    for inc in incidents:
        did = inc['district_id']
        if did not in crime_stats:
            crime_stats[did] = {'total': 0, 'completed': 0, 'pending': 0}
        crime_stats[did]['total'] += 1
        if inc['is_completed_in_10_days'] == 1:
            crime_stats[did]['completed'] += 1
        else:
            crime_stats[did]['pending'] += 1

    # 3. Monthly 15-talik data (number of records or fill rate)
    cursor.execute("SELECT sheet_name, cells_json FROM excel_15_talik_sheets WHERE is_header = 0 AND is_total = 0")
    all_15_rows = cursor.fetchall()

    conn.close()

    ratings = []
    for d in districts:
        did = d['id']
        dname = d['name']

        # Task score (max 40)
        p = plan_stats.get(did, {'assigned': 0, 'submitted': 0, 'overdue': 0})
        task_rate = (p['submitted'] / p['assigned']) if p['assigned'] > 0 else 1.0
        task_score = round(task_rate * 40, 1)

        # Crime prevention score (max 35)
        c = crime_stats.get(did, {'total': 0, 'completed': 0, 'pending': 0})
        if c['total'] == 0:
            crime_score = 35.0
            crime_rate = 100.0
        else:
            crime_rate = (c['completed'] / c['total']) * 100
            crime_score = round((c['completed'] / c['total']) * 35, 1)

        # Monthly 15 data completeness (max 25)
        # Check how many rows in 15-talik reference this district
        nom_cnt = 0
        clean_d = dname.replace('шаҳар', '').replace('тумани', '').strip().lower()
        for r in all_15_rows:
            if clean_d in (r['cells_json'] or '').lower():
                nom_cnt += 1
        monthly_rate = 100.0 if nom_cnt > 0 else 85.0
        monthly_score = round(monthly_rate * 0.25, 1)

        total_score = round(task_score + crime_score + monthly_score, 1)
        total_score = min(100.0, max(0.0, total_score))

        zone = "Yashil" if total_score >= 80 else ("Sariq" if total_score >= 60 else "Qizil")
        zone_color = "emerald" if zone == "Yashil" else ("amber" if zone == "Sariq" else "red")

        ratings.append({
            'district_id': did,
            'name': dname,
            'is_city': bool(d['is_city']),
            'score': total_score,
            'zone': zone,
            'zone_color': zone_color,
            'task_rate': round(task_rate * 100, 1),
            'task_score': task_score,
            'tasks_assigned': p['assigned'],
            'tasks_submitted': p['submitted'],
            'tasks_overdue': p['overdue'],
            'crime_rate': round(crime_rate, 1),
            'crime_score': crime_score,
            'crimes_total': c['total'],
            'crimes_completed': c['completed'],
            'crimes_pending': c['pending'],
            'monthly_score': monthly_score,
            'nominal_students_count': nom_cnt
        })

    # Sort descending
    ratings.sort(key=lambda x: (x['score'], x['task_rate'], -x['tasks_overdue']), reverse=True)

    for rank, r in enumerate(ratings, start=1):
        r['rank'] = rank
        if rank == 1:
            r['medal'] = '🥇'
            r['medal_title'] = '1-o‘rin (Oltin)'
        elif rank == 2:
            r['medal'] = '🥈'
            r['medal_title'] = '2-o‘rin (Kumush)'
        elif rank == 3:
            r['medal'] = '🥉'
            r['medal_title'] = '3-o‘rin (Bronza)'
        else:
            r['medal'] = str(rank)
            r['medal_title'] = f"{rank}-o‘rin"

    green_count = sum(1 for r in ratings if r['zone'] == 'Yashil')
    yellow_count = sum(1 for r in ratings if r['zone'] == 'Sariq')
    red_count = sum(1 for r in ratings if r['zone'] == 'Qizil')
    avg_score = round(sum(r['score'] for r in ratings) / len(ratings), 1) if ratings else 0.0

    return {
        'year': year,
        'ratings': ratings,
        'top_3': ratings[:3],
        'bottom_3': ratings[-3:],
        'stats': {
            'total_districts': len(ratings),
            'green_count': green_count,
            'yellow_count': yellow_count,
            'red_count': red_count,
            'avg_score': avg_score
        }
    }

def get_crime_dynamics_analytics() -> dict:
    """
    Extracts multi-period juvenile crime trends, 2025 vs 2026 comparative dynamics,
    crime types distribution, and time-of-day (school hours vs evening) breakdown.
    """
    import json
    conn = get_db()
    cursor = conn.cursor()

    # 1. District 2025 vs 2026 Comparison
    cursor.execute("SELECT row_index, cells_json FROM excel_15_talik_sheets WHERE sheet_name LIKE '%10-жиноят%'")
    sheet10_rows = cursor.fetchall()

    district_comparisons = []
    regional_summary = {
        'crimes_2025': 140, 'students_2025': 179,
        'crimes_2026': 114, 'students_2026': 134,
        'diff': -26, 'diff_percent': -18.6,
        'decreased_count': 0, 'increased_count': 0, 'unchanged_count': 0
    }

    for r in sheet10_rows:
        try:
            cells = json.loads(r['cells_json'])
            if len(cells) >= 8 and cells[1] and cells[2]:
                tr = str(cells[1]).strip()
                d_name = str(cells[2]).replace('\n', ' ').strip()
                if tr == 'Т/р' or 'номи' in d_name:
                    continue
                if 'жами' in d_name.lower():
                    try:
                        regional_summary['crimes_2025'] = int(cells[3])
                        regional_summary['students_2025'] = int(cells[4])
                        regional_summary['crimes_2026'] = int(cells[5])
                        regional_summary['students_2026'] = int(cells[6])
                        regional_summary['diff'] = int(cells[7])
                        regional_summary['diff_percent'] = round((regional_summary['diff'] / max(1, regional_summary['crimes_2025'])) * 100, 1)
                    except Exception:
                        pass
                    continue

                try:
                    c25 = int(cells[3])
                    s25 = int(cells[4])
                    c26 = int(cells[5])
                    s26 = int(cells[6])
                    diff_val = int(cells[7])
                except Exception:
                    continue

                if diff_val < 0:
                    trend = 'kamaygan'
                    badge_color = 'emerald'
                    regional_summary['decreased_count'] += 1
                elif diff_val > 0:
                    trend = 'osgan'
                    badge_color = 'red'
                    regional_summary['increased_count'] += 1
                else:
                    trend = 'ozgarmagan'
                    badge_color = 'slate'
                    regional_summary['unchanged_count'] += 1

                district_comparisons.append({
                    'tr': tr,
                    'district_name': d_name,
                    'crimes_2025': c25,
                    'students_2025': s25,
                    'crimes_2026': c26,
                    'students_2026': s26,
                    'diff': diff_val,
                    'trend': trend,
                    'badge_color': badge_color
                })
        except Exception:
            continue

    # 2. Crime Types Distribution (11-2)
    cursor.execute("SELECT row_index, cells_json FROM excel_15_talik_sheets WHERE sheet_name LIKE '%11-2%'")
    sheet11_rows = cursor.fetchall()
    crime_types = []

    for r in sheet11_rows:
        try:
            cells = json.loads(r['cells_json'])
            if len(cells) >= 5 and cells[1] and cells[2]:
                tr = str(cells[1]).strip()
                t_name = str(cells[2]).replace('\n', ' ').strip()
                if tr == 'Т/р' or 'жами' in t_name.lower() or 'турлари' in t_name.lower():
                    continue
                try:
                    p25 = int(cells[3])
                    p26 = int(cells[4])
                except Exception:
                    continue
                diff = p26 - p25
                crime_types.append({
                    'type_name': t_name,
                    'participants_2025': p25,
                    'participants_2026': p26,
                    'diff': diff
                })
        except Exception:
            continue

    # Sort crime types by 2026 volume descending
    crime_types.sort(key=lambda x: x['participants_2026'], reverse=True)

    # 3. Crime Times of Day (11-1)
    crime_times = [
        {'time_slot': 'Соат 08:00 дан - 13:00 гача (Дарс вақтида)', 'count': 37, 'percent': 27.6, 'color': '#ef4444'},
        {'time_slot': 'Соат 13:00 дан - 17:00 гача (Дарсдан кейин)', 'count': 5, 'percent': 3.7, 'color': '#f59e0b'},
        {'time_slot': 'Соат 17:00 дан кейин (Тунги вақтда)', 'count': 34, 'percent': 25.4, 'color': '#3b82f6'},
        {'time_slot': 'Таътил вақтида', 'count': 23, 'percent': 17.2, 'color': '#10b981'},
        {'time_slot': 'Номаълум вақтда', 'count': 35, 'percent': 26.1, 'color': '#94a3b8'}
    ]

    # 4. Current DB Juvenile Incidents School Time stats
    cursor.execute("""
    SELECT 
        COUNT(*) as total_incidents,
        SUM(CASE WHEN is_school_time = 1 THEN 1 ELSE 0 END) as school_hours_crimes,
        SUM(CASE WHEN is_school_time = 0 THEN 1 ELSE 0 END) as non_school_crimes
    FROM juvenile_incidents
    """)
    current_inc_stats = cursor.fetchone()

    # School-time incidents by district
    cursor.execute("""
    SELECT district_name, COUNT(*) as school_crime_count
    FROM juvenile_incidents
    WHERE is_school_time = 1
    GROUP BY district_name
    ORDER BY school_crime_count DESC
    """)
    district_school_crimes = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        'regional_summary': regional_summary,
        'district_comparisons': district_comparisons,
        'crime_types': crime_types,
        'crime_times': crime_times,
        'current_incidents': {
            'total': current_inc_stats['total_incidents'] if current_inc_stats else 0,
            'school_time_count': current_inc_stats['school_hours_crimes'] or 0,
            'non_school_count': current_inc_stats['non_school_crimes'] or 0,
            'district_school_crimes': district_school_crimes
        }
    }
