# -*- coding: utf-8 -*-
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import json
import shutil
import zipfile
from pydantic import BaseModel
from typing import List, Optional
from fastapi import FastAPI, Request, Response, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from app.db import get_db, init_db, log_audit
from app.services.report_generator import (
    generate_crime_analytical_word, generate_15_talik_excel, 
    generate_incidents_excel, generate_discipline_rating, 
    MONTH_NAMES_UZ, EXPORTS_DIR
)
from app.services.notification_service import (
    run_deadline_checks,
    send_telegram_message,
    broadcast_deadline_alerts_to_telegram
)
from app.parsers.parse_work_plans import parse_and_import_work_plan
from app.parsers.parse_incidents import import_monthly_incidents_file
from app.services.ai_service import (
    analyze_incident_ai,
    evaluate_actions_ai,
    generate_executive_briefing_ai,
    evaluate_district_report_ai
)
from app.parsers.cache_15_talik_exact import reload_15_talik_from_file
from datetime import datetime
from app.services.storage_service import (
    save_uploaded_files_and_passport,
    get_assignment_storage_path,
    open_folder_in_windows_explorer,
    BASE_STORAGE_DIR,
    sanitize_filename
)
from app.services.plan_analytics import (
    get_work_plan_matrix,
    generate_plan_analytical_excel,
    calculate_district_kpi_ratings,
    get_crime_dynamics_analytics
)
from app.services.sync_service import (
    get_sync_manifest,
    resolve_sync_file_path,
    create_full_sync_archive
)
from app.services.monthly_15_service import (
    get_sheet_columns,
    is_nominal_sheet,
    save_svod_district_row,
    add_nominal_record,
    update_nominal_record,
    delete_nominal_record,
    generate_nominal_template,
    import_nominal_excel,
    get_svod_target_count,
    get_district_nominal_records
)
from app.auth import (
    authenticate_user,
    create_session,
    delete_session,
    get_current_user,
    update_user_password,
    reset_district_password,
    get_all_district_users
)

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    new_password: str

class ResetPasswordRequest(BaseModel):
    user_id: int

class SvodSaveRequest(BaseModel):
    sheet_name: str
    district_name: str
    cells: List[str]
    user_name: Optional[str] = "Tuman mas'uli"

class NominalAddRequest(BaseModel):
    sheet_name: str
    district_name: str
    cells: List[str]
    user_name: Optional[str] = "Tuman mas'uli"

class NominalUpdateRequest(BaseModel):
    sheet_name: str
    row_index: int
    cells: List[str]
    user_name: Optional[str] = "Tuman mas'uli"

class NominalDeleteRequest(BaseModel):
    sheet_name: str
    row_index: int
    user_name: Optional[str] = "Tuman mas'uli"

app = FastAPI(title="Farg‘ona MMTB Ijro Nazorati va Monitoring Tizimi")

# Static files and Templates
STATIC_DIR = os.path.join(CURRENT_DIR, "static")
TEMPLATES_DIR = os.path.join(CURRENT_DIR, "templates")
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@app.on_event("startup")
async def startup_event():
    init_db()
    run_deadline_checks()

# ==================== AUTHENTICATION ROUTES ====================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        if user.get("role") == "district":
            return RedirectResponse(url="/district-portal", status_code=302)
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
async def login_api(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=400, detail="Login yoki parol noto‘g‘ri!")

    redirect_url = "/district-portal" if user['role'] == 'district' else "/"
    res = JSONResponse({
        "status": "success",
        "redirect_url": redirect_url,
        "user": user
    })
    create_session(user['id'], res)
    log_audit("Tizimga Kirish", f"{user['fio']} ({user['username']}) tizimga muvaffaqiyatli kirdi.", user_fio=user['fio'], user_id=user['id'])
    return res

@app.get("/logout")
async def logout_endpoint(request: Request, response: Response):
    user = get_current_user(request)
    if user:
        log_audit("Tizimdan Chiqish", f"{user['fio']} tizimdan chiqdi.", user_fio=user['fio'], user_id=user['id'])
    resp = RedirectResponse(url="/login", status_code=302)
    delete_session(request, resp)
    return resp

@app.post("/api/auth/change-password")
async def change_password_api(request: Request, req: ChangePasswordRequest):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Avtorizatsiyadan o‘tilmagan")

    success = update_user_password(user['id'], req.new_password)
    if not success:
        raise HTTPException(status_code=400, detail="Parol kamida 3 ta belgidan iborat bo‘lishi kerak")

    return JSONResponse({"status": "success", "message": "Parol muvaffaqiyatli yangilandi!"})

@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") == "district":
        return RedirectResponse(url="/district-portal", status_code=302)

    users_list = get_all_district_users()
    return templates.TemplateResponse(request=request, name="admin_users.html", context={
        "current_user": user,
        "users": users_list
    })

@app.post("/api/admin/reset-district-password")
async def reset_password_api(request: Request, req: ResetPasswordRequest):
    admin_user = get_current_user(request)
    if not admin_user or admin_user.get("role") == "district":
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan")

    success = reset_district_password(req.user_id, admin_fio=admin_user['fio'])
    if not success:
        raise HTTPException(status_code=400, detail="Xatolik yuz berdi")

    return JSONResponse({"status": "success", "message": "Parol '123' ga qaytarildi."})

@app.get("/district-portal", response_class=HTMLResponse)
async def district_portal_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    dist_id = user.get("district_id") or 1

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT a.*, d.name as district_name, u.fio as assigned_by_fio,
           p.id as proof_id, p.proof_text, p.response_letter_number, p.response_letter_date,
           p.response_letter_path, p.basis_attachments, p.attachment_paths, p.approval_status as proof_status,
           p.rejection_reason, p.submitted_at as proof_submitted_at,
           (SELECT COUNT(*) FROM execution_proofs WHERE target_type = 'task_district_assignment' AND target_id = a.id) as proof_count
    FROM task_district_assignments a
    JOIN districts d ON a.district_id = d.id
    LEFT JOIN users u ON a.assigned_by_user_id = u.id
    LEFT JOIN (
        SELECT ep.*
        FROM execution_proofs ep
        INNER JOIN (
            SELECT target_id, MAX(id) as max_id
            FROM execution_proofs
            WHERE target_type = 'task_district_assignment'
            GROUP BY target_id
        ) latest ON ep.id = latest.max_id
    ) p ON p.target_id = a.id
    WHERE a.district_id = ?
    ORDER BY a.id DESC
    """, (dist_id,))
    assignments_raw = cursor.fetchall()
    assignments = []
    for a in assignments_raw:
        item = dict(a)
        basis_list = []
        if item.get("basis_attachments"):
            try:
                basis_list = json.loads(item["basis_attachments"])
            except Exception:
                basis_list = []
        item["basis_list"] = basis_list
        assignments.append(item)

    cursor.execute("""
    SELECT i.*, a.school_responsible_fio, a.inspector_fio, a.current_study_status
    FROM juvenile_incidents i
    LEFT JOIN incident_actions a ON a.incident_id = i.id
    WHERE i.district_id = ?
    ORDER BY i.days_remaining ASC
    """, (dist_id,))
    incidents = cursor.fetchall()

    cursor.execute("SELECT * FROM districts WHERE id = ?", (dist_id,))
    dist = cursor.fetchone()
    school_cnt = 54 if not dist['is_city'] else 41

    cursor.execute("""
    SELECT numeric_values FROM monthly_15_records r 
    JOIN monthly_15_submissions s ON r.submission_id = s.id 
    WHERE s.district_id = ? AND r.direction_number = 10 LIMIT 1
    """, (dist_id,))
    c_row = cursor.fetchone()
    crime_vals = json.loads(c_row['numeric_values']) if c_row and c_row['numeric_values'] else {}
    j25 = crime_vals.get('jinoyat_2025', 0)
    j26 = crime_vals.get('jinoyat_2026', 0)
    diff = crime_vals.get('farqi', j26 - j25)

    risk_level = "Yuqori (Qizil hudud)" if diff > 0 else ("O‘rtacha (Sariq hudud)" if diff == 0 else "Namunali (Yashil hudud)")
    risk_color = "red" if diff > 0 else ("amber" if diff == 0 else "emerald")

    conn.close()

    dossier = {
        "schools_count": school_cnt,
        "crime_2025": j25,
        "crime_2026": j26,
        "crime_diff": diff,
        "risk_level": risk_level,
        "risk_color": risk_color
    }

    return templates.TemplateResponse(request=request, name="district_portal.html", context={
        "current_user": user,
        "dossier": dossier,
        "assignments": assignments,
        "incidents": incidents
    })

# ==================== HTML ROUTES ====================

@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") == "district":
        return RedirectResponse(url="/district-portal", status_code=302)
    conn = get_db()
    cursor = conn.cursor()

    # KPI counts
    cursor.execute("SELECT COUNT(*) as cnt FROM work_plan_items")
    total_tasks = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) as cnt FROM work_plan_items WHERE status = 'Bajarildi'")
    done_tasks = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) as cnt FROM task_district_assignments")
    total_assignments = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) as cnt FROM juvenile_incidents")
    total_incidents = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) as cnt FROM juvenile_incidents WHERE days_remaining <= 3 AND status = 'Nazoratda'")
    critical_incidents = cursor.fetchone()['cnt']

    # 19 Districts summary for interactive grid
    cursor.execute("""
    SELECT d.id, d.name, d.is_city,
           (SELECT COUNT(*) FROM task_district_assignments WHERE district_id = d.id) as assigned_tasks,
           (SELECT COUNT(*) FROM juvenile_incidents WHERE district_id = d.id) as incident_count,
           (SELECT numeric_values FROM monthly_15_records r 
            JOIN monthly_15_submissions s ON r.submission_id = s.id 
            WHERE s.district_id = d.id AND r.direction_number = 10 LIMIT 1) as crime_data
    FROM districts d
    ORDER BY d.sort_order
    """)
    districts = cursor.fetchall()

    districts_list = []
    chart_labels = []
    chart_2025 = []
    chart_2026 = []

    for d in districts:
        c_data = json.loads(d['crime_data']) if d['crime_data'] else {}
        j25 = c_data.get('jinoyat_2025', 0)
        j26 = c_data.get('jinoyat_2026', 0)
        diff = c_data.get('farqi', j26 - j25)

        chart_labels.append(d['name'].replace('шаҳар','sh.').replace('тумани','t.'))
        chart_2025.append(j25)
        chart_2026.append(j26)

        status_color = "red" if diff > 0 else ("green" if diff < 0 else "blue")
        districts_list.append({
            'id': d['id'],
            'name': d['name'],
            'assigned_tasks': d['assigned_tasks'],
            'incident_count': d['incident_count'],
            'j25': j25,
            'j26': j26,
            'diff': diff,
            'status_color': status_color
        })

    # Recent notifications
    cursor.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 6")
    notifications = cursor.fetchall()

    conn.close()
    return templates.TemplateResponse(request=request, name="index.html", context={
        "current_user": user,
        "total_tasks": total_tasks,
        "done_tasks": done_tasks,
        "total_assignments": total_assignments,
        "total_incidents": total_incidents,
        "critical_incidents": critical_incidents,
        "districts": districts_list,
        "chart_labels": json.dumps(chart_labels),
        "chart_2025": json.dumps(chart_2025),
        "chart_2026": json.dumps(chart_2026),
        "notifications": notifications
    })

@app.get("/work-plans", response_class=HTMLResponse)
async def work_plans_page(request: Request, curator: str = "all", section: int = 1):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") == "district":
        return RedirectResponse(url="/district-portal", status_code=302)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, owner_fio, title FROM work_plans ORDER BY id ASC")
    curators = cursor.fetchall()

    query = """
    SELECT i.*, p.owner_fio, d.name as target_district_name
    FROM work_plan_items i
    JOIN work_plans p ON i.plan_id = p.id
    LEFT JOIN districts d ON i.target_district_id = d.id
    WHERE 1=1
    """
    params = []
    if curator != "all":
        query += " AND p.owner_fio LIKE ?"
        params.append(f"%{curator}%")
    if section > 0:
        query += " AND i.section_number = ?"
        params.append(section)

    query += " ORDER BY i.id ASC"
    cursor.execute(query, params)
    items = cursor.fetchall()

    cursor.execute("SELECT id, name FROM districts ORDER BY sort_order")
    all_districts = cursor.fetchall()

    conn.close()
    return templates.TemplateResponse(request=request, name="work_plans.html", context={
        "current_user": user,
        "curators": curators,
        "selected_curator": curator,
        "selected_section": section,
        "items": items,
        "all_districts": all_districts
    })

@app.get("/work-plans/matrix", response_class=HTMLResponse)
async def work_plans_matrix_page(request: Request, year: int = 2026, curator: str = "all"):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") == "district":
        return RedirectResponse(url="/district-portal", status_code=302)

    matrix_data = get_work_plan_matrix(year=year, curator=curator)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT owner_fio FROM work_plans WHERE year = ?", (year,))
    curators = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(request=request, name="work_plan_matrix.html", context={
        "current_user": user,
        "matrix_data": matrix_data,
        "selected_year": year,
        "selected_curator": curator,
        "curators": curators,
        "base_storage_dir": BASE_STORAGE_DIR
    })

@app.get("/district-assignments", response_class=HTMLResponse)
async def district_assignments_page(request: Request, district_id: int = 0, filter_type: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") == "district":
        district_id = user.get("district_id", 0)

    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT a.*, d.name as district_name, u.fio as assigned_by_fio,
           p.id as proof_id, p.proof_text, p.response_letter_number, p.response_letter_date,
           p.response_letter_path, p.basis_attachments, p.attachment_paths, p.approval_status as proof_status,
           p.rejection_reason, p.submitted_at as proof_submitted_at, p.submitted_by_fio as proof_submitted_by,
           (SELECT COUNT(*) FROM execution_proofs WHERE target_type = 'task_district_assignment' AND target_id = a.id) as proof_count
    FROM task_district_assignments a
    JOIN districts d ON a.district_id = d.id
    LEFT JOIN users u ON a.assigned_by_user_id = u.id
    LEFT JOIN (
        SELECT ep.*
        FROM execution_proofs ep
        INNER JOIN (
            SELECT target_id, MAX(id) as max_id
            FROM execution_proofs
            WHERE target_type = 'task_district_assignment'
            GROUP BY target_id
        ) latest ON ep.id = latest.max_id
    ) p ON p.target_id = a.id
    WHERE 1=1
    """
    params = []
    if district_id > 0:
        query += " AND a.district_id = ?"
        params.append(district_id)

    if filter_type == "iib":
        query += " AND a.doc_type = 'IIB taqdimnomasi'"
    elif filter_type == "murojaat":
        query += " AND a.doc_type = 'Fuqaro murojaati'"
    elif filter_type == "topshiriq":
        query += " AND (a.doc_type NOT IN ('IIB taqdimnomasi', 'Fuqaro murojaati') OR a.doc_type IS NULL)"
    elif filter_type == "submitted":
        query += " AND a.status IN ('Hisobot topshirildi', 'Tasdiqlandi')"
    elif filter_type == "pending":
        query += " AND a.status IN ('Yangi', 'Kutilmoqda')"

    query += " ORDER BY a.id DESC"
    cursor.execute(query, params)
    assignments_raw = cursor.fetchall()
    assignments = []
    for a in assignments_raw:
        item = dict(a)
        basis_list = []
        if item.get("basis_attachments"):
            try:
                basis_list = json.loads(item["basis_attachments"])
            except Exception:
                basis_list = []
        item["basis_list"] = basis_list
        assignments.append(item)

    cursor.execute("SELECT id, name FROM districts ORDER BY sort_order")
    districts = cursor.fetchall()

    stats_query = """
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN doc_type = 'IIB taqdimnomasi' THEN 1 ELSE 0 END) as iib_count,
        SUM(CASE WHEN doc_type = 'Fuqaro murojaati' THEN 1 ELSE 0 END) as murojaat_count,
        SUM(CASE WHEN doc_type NOT IN ('IIB taqdimnomasi', 'Fuqaro murojaati') THEN 1 ELSE 0 END) as topshiriq_count,
        SUM(CASE WHEN status IN ('Hisobot topshirildi', 'Tasdiqlandi') THEN 1 ELSE 0 END) as submitted_count,
        SUM(CASE WHEN status = 'Tasdiqlandi' THEN 1 ELSE 0 END) as approved_count,
        SUM(CASE WHEN status = 'Qaytarildi' THEN 1 ELSE 0 END) as returned_count,
        SUM(CASE WHEN status IN ('Yangi', 'Kutilmoqda') THEN 1 ELSE 0 END) as pending_count
    FROM task_district_assignments
    """
    if district_id > 0:
        stats_query += " WHERE district_id = ?"
        cursor.execute(stats_query, [district_id])
    else:
        cursor.execute(stats_query)
    stats = cursor.fetchone()

    conn.close()
    return templates.TemplateResponse(request=request, name="district_assignments.html", context={
        "current_user": user,
        "assignments": assignments,
        "districts": districts,
        "selected_district": district_id,
        "selected_filter": filter_type,
        "stats": stats or {}
    })

@app.get("/monthly-15", response_class=HTMLResponse)
async def monthly_15_page(request: Request, sheet: str = "1-Нотинч", district: str = "all"):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") == "district":
        district = user.get("district_name", district)
    conn = get_db()
    cursor = conn.cursor()

    # Get all distinct sheets
    cursor.execute("SELECT DISTINCT sheet_index, sheet_name FROM excel_15_talik_sheets ORDER BY sheet_index")
    sheet_rows = cursor.fetchall()
    sheet_names = [r['sheet_name'] for r in sheet_rows]

    if not sheet_names:
        from app.parsers.cache_15_talik_exact import init_15_talik_exact_cache
        init_15_talik_exact_cache()
        cursor.execute("SELECT DISTINCT sheet_index, sheet_name FROM excel_15_talik_sheets ORDER BY sheet_index")
        sheet_rows = cursor.fetchall()
        sheet_names = [r['sheet_name'] for r in sheet_rows]

    if sheet not in sheet_names and sheet_names:
        sheet = sheet_names[0]

    # Fetch 19 districts
    cursor.execute("SELECT id, name, code, is_city FROM districts ORDER BY sort_order")
    all_districts = [dict(d) for d in cursor.fetchall()]
    district_names = [d['name'] for d in all_districts]

    cursor.execute("""
    SELECT row_index, cells_json, is_header, is_total 
    FROM excel_15_talik_sheets 
    WHERE sheet_name = ? 
    ORDER BY row_index
    """, (sheet,))
    db_rows = cursor.fetchall()

    is_nominal = is_nominal_sheet(sheet)
    columns = get_sheet_columns(sheet)

    table_rows = []
    current_section_district = ""

    for r in db_rows:
        cells = json.loads(r['cells_json'])
        is_hdr = bool(r['is_header'])
        is_tot = bool(r['is_total'])
        row_str = " ".join(str(x) for x in cells)

        # Check district association
        row_district = ""
        is_section_hdr = False

        if len(cells) <= 4 and any(d in row_str for d in district_names):
            for d in district_names:
                if d in row_str:
                    current_section_district = d
                    row_district = d
                    is_section_hdr = True
                    break
        else:
            for d in district_names:
                if any(d in str(c) for c in cells):
                    row_district = d
                    break

        if not row_district and not is_hdr and not is_tot:
            row_district = current_section_district

        # Strict multi-tenant isolation: District user only receives header rows and their own district data
        if user and user.get("role") == "district":
            user_dist = user.get("district_name", "")
            user_clean = user_dist.replace("тумани", "").replace("шаҳар", "").replace("шаҳри", "").strip().lower()
            row_clean = row_district.replace("тумани", "").replace("шаҳар", "").replace("шаҳри", "").strip().lower() if row_district else ""
            
            # Allow header rows (to display table columns), and rows belonging to this district
            if not is_hdr and (not row_clean or row_clean != user_clean):
                continue

        is_selected = (district != "all" and row_district == district)

        table_rows.append({
            'row_index': r['row_index'],
            'cells': cells,
            'is_header': is_hdr,
            'is_total': is_tot,
            'district_name': row_district,
            'is_section_header': is_section_hdr,
            'is_selected_district': is_selected
        })

    reconciliation = None
    if is_nominal:
        target_dist = user.get("district_name") if (user and user.get("role") == "district") else (district if district != "all" else "")
        if target_dist:
            svod_info = get_svod_target_count(target_dist, sheet)
            records = get_district_nominal_records(sheet, target_dist)
            target_count = svod_info.get("target_count", 0)
            curr_count = len(records)
            reconciliation = {
                "district_name": target_dist,
                "has_svod": svod_info.get("has_svod", False),
                "svod_sheet": svod_info.get("svod_sheet", ""),
                "svod_title": svod_info.get("title", ""),
                "target_count": target_count,
                "current_count": curr_count,
                "diff": curr_count - target_count,
                "is_matched": (curr_count == target_count if target_count > 0 else True)
            }

    conn.close()
    return templates.TemplateResponse(request=request, name="monthly_15.html", context={
        "current_user": user,
        "sheet_names": sheet_names,
        "selected_sheet": sheet,
        "selected_district": district,
        "districts": all_districts,
        "is_nominal": is_nominal,
        "columns": columns,
        "columns_json": json.dumps(columns, ensure_ascii=False),
        "table_rows": table_rows,
        "reconciliation": reconciliation
    })

# ==================== MONTHLY-15 CRUD APIS ====================

@app.get("/api/monthly-15/meta")
async def get_monthly_15_meta(sheet: str = "1-Нотинч"):
    cols = get_sheet_columns(sheet)
    nominal = is_nominal_sheet(sheet)
    return JSONResponse({
        "status": "success",
        "sheet_name": sheet,
        "is_nominal": nominal,
        "columns": cols
    })

@app.post("/api/monthly-15/save-svod")
async def api_save_svod(request: Request, req: SvodSaveRequest):
    user = get_current_user(request)
    if user and user.get("role") == "district":
        if req.district_name.lower().strip() != user.get("district_name", "").lower().strip():
            raise HTTPException(status_code=403, detail="Siz faqat o‘z tumaningiz ko‘rsatkichlarini tahrirlay olasiz!")
        req.user_name = user.get("fio", req.user_name)

    success, msg = save_svod_district_row(
        sheet_name=req.sheet_name,
        district_name=req.district_name,
        updated_cells=req.cells,
        user_name=req.user_name
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return JSONResponse({"status": "success", "message": msg})

@app.post("/api/monthly-15/add-nominal")
async def api_add_nominal(request: Request, req: NominalAddRequest):
    user = get_current_user(request)
    if user and user.get("role") == "district":
        req.district_name = user.get("district_name", req.district_name)
        req.user_name = user.get("fio", req.user_name)

    success, msg = add_nominal_record(
        sheet_name=req.sheet_name,
        district_name=req.district_name,
        row_data=req.cells,
        user_name=req.user_name
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return JSONResponse({"status": "success", "message": msg})

@app.post("/api/monthly-15/update-nominal")
async def api_update_nominal(request: Request, req: NominalUpdateRequest):
    user = get_current_user(request)
    if user and user.get("role") == "district":
        req.user_name = user.get("fio", req.user_name)

    success, msg = update_nominal_record(
        sheet_name=req.sheet_name,
        row_index=req.row_index,
        row_data=req.cells,
        user_name=req.user_name
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return JSONResponse({"status": "success", "message": msg})

@app.post("/api/monthly-15/delete-row")
async def api_delete_nominal(request: Request, req: NominalDeleteRequest):
    user = get_current_user(request)
    if user and user.get("role") == "district":
        req.user_name = user.get("fio", req.user_name)

    success, msg = delete_nominal_record(
        sheet_name=req.sheet_name,
        row_index=req.row_index,
        user_name=req.user_name
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return JSONResponse({"status": "success", "message": msg})

@app.get("/api/monthly-15/nominal-template")
async def api_download_nominal_template(request: Request, sheet: str, district: str = ""):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Tizimga kiring")
    if user.get("role") == "district":
        district = user.get("district_name", district)
    
    import urllib.parse
    filename, file_bytes = generate_nominal_template(sheet, district)
    safe_ascii_name = f"Shablon_{sheet[:10].encode('ascii', 'ignore').decode() or 'Nominal'}.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_ascii_name}"; filename*=UTF-8\'\'{encoded_filename}'
        }
    )

@app.get("/api/monthly-15/reconciliation-status")
async def api_reconciliation_status(request: Request, sheet: str, district: str = ""):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Tizimga kiring")
    if user.get("role") == "district":
        district = user.get("district_name", district)
    elif not district or district == "all":
        district = "Бувайда тумани"
        
    svod_info = get_svod_target_count(district, sheet)
    existing = get_district_nominal_records(sheet, district)
    current_count = len(existing)
    target_count = svod_info.get("target_count", 0)
    diff = current_count - target_count
    
    return JSONResponse({
        "status": "success",
        "sheet_name": sheet,
        "district_name": district,
        "has_svod": svod_info.get("has_svod", False),
        "svod_sheet": svod_info.get("svod_sheet", ""),
        "svod_title": svod_info.get("title", ""),
        "target_count": target_count,
        "current_count": current_count,
        "diff": diff,
        "is_matched": (diff == 0 if target_count > 0 else True)
    })

@app.post("/api/monthly-15/import-nominal-excel")
async def api_import_nominal_excel(
    request: Request,
    file: UploadFile = File(...),
    sheet_name: str = Form(...),
    district_name: str = Form(...),
    mode: str = Form("append")
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Tizimga kiring")
    
    if user.get("role") == "district":
        district_name = user.get("district_name", district_name)
    
    user_name = user.get("fio", "Tuman mas'uli")
    file_bytes = await file.read()
    
    result = import_nominal_excel(
        file_bytes=file_bytes,
        sheet_name=sheet_name,
        district_name=district_name,
        mode=mode,
        user_name=user_name
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Importda xatolik yuz berdi"))
        
    return JSONResponse(result)

# ==================== CLOUD / LOCAL AUTO-SYNC APIS ====================

@app.get("/api/sync/manifest")
async def api_sync_manifest():
    """Returns the manifest of all district files and latest 15-talik Excel for auto-sync."""
    manifest = get_sync_manifest()
    return JSONResponse(manifest)

@app.get("/api/sync/file")
async def api_sync_download_file(category: str, rel_path: str):
    """Downloads a single file for the auto-sync agent."""
    file_path = resolve_sync_file_path(category, rel_path)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Fayl topilmadi")
    
    fname = os.path.basename(file_path)
    return FileResponse(path=file_path, filename=fname)

@app.get("/api/sync/full-archive")
async def api_sync_full_archive():
    """Generates and streams a full ZIP archive of all files for instant offline sync."""
    zip_filename, zip_bytes = create_full_sync_archive()
    import urllib.parse
    encoded_name = urllib.parse.quote(zip_filename)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"; filename*=UTF-8\'\'{encoded_name}'
        }
    )

@app.get("/incidents", response_class=HTMLResponse)
async def incidents_page(request: Request, search: str = "", district_id: int = 0, school_time: int = -1):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") == "district":
        district_id = user.get("district_id", 0)

    conn = get_db()
    cursor = conn.cursor()

    query = """
    SELECT i.*, a.school_responsible_fio, a.mfy_responsible_fio, a.inspector_fio, 
           a.current_study_status, a.is_completed_in_10_days
    FROM juvenile_incidents i
    LEFT JOIN incident_actions a ON a.incident_id = i.id
    WHERE 1=1
    """
    params = []
    if search:
        query += " AND (i.student_fio LIKE ? OR i.school_name LIKE ? OR i.criminal_article LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if district_id > 0:
        query += " AND i.district_id = ?"
        params.append(district_id)
    if school_time == 1:
        query += " AND i.is_school_time = 1"
    elif school_time == 0:
        query += " AND i.is_school_time = 0"

    query += " ORDER BY i.is_new DESC, i.is_school_time DESC, i.id DESC"
    cursor.execute(query, params)
    incidents = cursor.fetchall()

    cursor.execute("SELECT id, name FROM districts ORDER BY sort_order")
    districts = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_school_time = 1 THEN 1 ELSE 0 END) as school_cnt, SUM(CASE WHEN days_remaining <= 3 AND status='Nazoratda' THEN 1 ELSE 0 END) as urgent_cnt FROM juvenile_incidents")
    stats_row = cursor.fetchone()
    stats = {
        'total': stats_row['total'] if stats_row else len(incidents),
        'school_cnt': stats_row['school_cnt'] or 0,
        'urgent_cnt': stats_row['urgent_cnt'] or 0
    }

    conn.close()
    return templates.TemplateResponse(request=request, name="incidents.html", context={
        "current_user": user,
        "incidents": incidents,
        "districts": districts,
        "search": search,
        "selected_district": district_id,
        "school_time": school_time,
        "stats": stats
    })

@app.post("/api/incidents/upload-monthly-excel")
async def upload_monthly_incidents_excel(
    request: Request,
    file: UploadFile = File(...),
    auto_ai: bool = Form(False)
):
    user = get_current_user(request)
    if not user or user.get("role") == "district":
        raise HTTPException(status_code=403, detail="Faqat administratorlar oylik fayl yuklashi mumkin")
    
    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        raise HTTPException(status_code=400, detail="Faqat Excel (.xlsx) fayli qabul qilinadi")

    temp_path = os.path.join(UPLOADS_DIR, f"incidents_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    res = import_monthly_incidents_file(temp_path, auto_ai_analyze=auto_ai)
    log_audit("Oylik jinoyatchilik yuklandi", f"{file.filename}: {res.get('new_count', 0)} ta yangi, {res.get('existing_count', 0)} ta mavjud holat")
    return JSONResponse(res)

@app.post("/api/incidents/{incident_id}/analyze-ai")
async def trigger_incident_ai(incident_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM juvenile_incidents WHERE id = ?", (incident_id,))
    inc = cursor.fetchone()
    if not inc:
        conn.close()
        raise HTTPException(status_code=404, detail="Hodisa topilmadi")
    
    ai_res = analyze_incident_ai(
        student_fio=inc['student_fio'],
        district_name=inc['district_name'],
        school_name=inc['school_name'] or '',
        article=inc['criminal_article'] or '',
        details=inc['incident_details'] or '',
        birth_date=inc['birth_date'] or ''
    )
    
    tavsiyalar_json = json.dumps(ai_res.get("tavsiyalar", []), ensure_ascii=False)
    cursor.execute("""
    UPDATE juvenile_incidents
    SET ai_analysis = ?, ai_risk_level = ?, ai_recommendations = ?, ai_letter_draft = ?
    WHERE id = ?
    """, (
        ai_res.get("sabab", ""),
        ai_res.get("xavf_darajasi", "O‘rta"),
        tavsiyalar_json,
        ai_res.get("talabnoma_xati", ""),
        incident_id
    ))
    conn.commit()
    conn.close()
    return JSONResponse({"status": "success", "ai": ai_res})

@app.get("/api/incidents/{incident_id}/ai-result")
async def get_incident_ai(incident_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, student_fio, district_name, school_name, criminal_article, 
           incident_details, ai_analysis, ai_risk_level, ai_recommendations, ai_letter_draft,
           days_remaining, status, is_new
    FROM juvenile_incidents WHERE id = ?
    """, (incident_id,))
    inc = cursor.fetchone()
    conn.close()
    if not inc:
        raise HTTPException(status_code=404, detail="Hodisa topilmadi")
    
    tavsiyalar = []
    if inc['ai_recommendations']:
        try:
            tavsiyalar = json.loads(inc['ai_recommendations'])
        except Exception:
            tavsiyalar = [inc['ai_recommendations']]

    return JSONResponse({
        "status": "success",
        "id": inc['id'],
        "student_fio": inc['student_fio'],
        "district_name": inc['district_name'],
        "school_name": inc['school_name'],
        "article": inc['criminal_article'],
        "details": inc['incident_details'],
        "ai_analysis": inc['ai_analysis'],
        "ai_risk_level": inc['ai_risk_level'] or 'O‘rta',
        "ai_recommendations": tavsiyalar,
        "ai_letter_draft": inc['ai_letter_draft'],
        "days_remaining": inc['days_remaining'],
        "is_new": inc['is_new']
    })

# ==================== KPI RATINGS & EXECUTIVE AI BRIEFING ====================

@app.get("/ratings", response_class=HTMLResponse)
async def ratings_page(request: Request, year: int = 2026):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    kpi_data = calculate_district_kpi_ratings(year=year)
    return templates.TemplateResponse(request=request, name="ratings.html", context={
        "current_user": user,
        "kpi": kpi_data,
        "current_year": year
    })

@app.get("/dynamics", response_class=HTMLResponse)
async def crime_dynamics_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    data = get_crime_dynamics_analytics()
    return templates.TemplateResponse(request=request, name="crime_dynamics.html", context={
        "current_user": user,
        "data": data
    })

@app.get("/api/analytics/crime-dynamics")
async def get_crime_dynamics_api(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Tizimga kiring")
    return JSONResponse(get_crime_dynamics_analytics())

@app.post("/api/ai/executive-briefing")
async def trigger_executive_briefing(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") == "district":
        raise HTTPException(status_code=403, detail="Faqat administratorlar uchun")
    
    kpi = calculate_district_kpi_ratings(year=2026)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN days_remaining <= 3 AND status='Nazoratda' THEN 1 ELSE 0 END) as urgent FROM juvenile_incidents")
    crow = cursor.fetchone()
    cursor.execute("SELECT district_name, COUNT(*) as cnt FROM juvenile_incidents GROUP BY district_name ORDER BY cnt DESC LIMIT 3")
    hotspots = [f"{r['district_name']} ({r['cnt']} ta)" for r in cursor.fetchall()]
    
    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status='Bajarildi' THEN 1 ELSE 0 END) as comp, SUM(CASE WHEN status='Kechikmoqda' THEN 1 ELSE 0 END) as over FROM work_plan_items")
    prow = cursor.fetchone()
    conn.close()

    crime_stats = {
        "total": crow['total'] if crow and crow['total'] else 0,
        "urgent": crow['urgent'] if crow and crow['urgent'] else 0,
        "hotspots": ", ".join(hotspots) if hotspots else "Mavjud emas"
    }
    plan_stats = {
        "total": prow['total'] if prow and prow['total'] else 0,
        "completed": prow['comp'] if prow and prow['comp'] else 0,
        "overdue": prow['over'] if prow and prow['over'] else 0
    }

    briefing = generate_executive_briefing_ai(kpi['ratings'], crime_stats, plan_stats, period_name="Haftalik")
    log_audit("AI Rahbariyat Tahlili", "Boshqarma apparat yig‘ilishi uchun Gemini AI axborotnomasi shakllantirildi")
    return JSONResponse(briefing)

@app.post("/api/admin/send-deadline-alerts")
async def trigger_deadline_alerts(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") == "district":
        raise HTTPException(status_code=403, detail="Faqat administratorlar uchun")
    res = broadcast_deadline_alerts_to_telegram()
    log_audit("Telegram Eslatmalar", f"Ijro nazorati bo‘yicha {res.get('alerts_count', 0)} ta eslatma tarqatildi")
    return JSONResponse(res)

@app.post("/api/admin/telegram-test")
async def test_telegram_api(chat_id: str = Form(...), message: str = Form("Farg‘ona MMTB: Test xabarnomasi muvaffaqiyatli yetkazildi!")):
    res = send_telegram_message(chat_id, message)
    return JSONResponse(res)

@app.post("/api/work-plans/create-custom-plan")
async def create_custom_work_plan(
    request: Request,
    title: str = Form(...),
    owner_fio: str = Form(...),
    owner_role: str = Form("Mas’ul ijrochi"),
    year: int = Form(2026)
):
    user = get_current_user(request)
    if not user or user.get("role") == "district":
        raise HTTPException(status_code=403, detail="Faqat administratorlar yangi reja yaratishi mumkin")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO work_plans (user_id, owner_fio, owner_role, year, title, source_filename, status)
    VALUES (?, ?, ?, ?, ?, 'Platformada yaratilgan', 'Tasdiqlangan')
    """, (user.get('id'), owner_fio.strip(), owner_role.strip(), year, title.strip()))
    plan_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log_audit("Yangi Ish Rejasi Yaratildi", f"'{title}' ({owner_fio}) rejasi yaratildi")
    return JSONResponse({"status": "success", "plan_id": plan_id, "message": f"'{title}' muvaffaqiyatli yaratildi!"})

@app.get("/api/students/unified-passport")
async def get_student_unified_passport(fio: str, district: str = ""):
    conn = get_db()
    cursor = conn.cursor()
    clean_fio = fio.strip()
    
    # 1. Juvenile incidents
    cursor.execute("""
    SELECT i.*, a.school_responsible_fio, a.mfy_responsible_fio, a.inspector_fio, a.current_study_status
    FROM juvenile_incidents i
    LEFT JOIN incident_actions a ON a.incident_id = i.id
    WHERE i.student_fio LIKE ?
    LIMIT 5
    """, (f"%{clean_fio}%",))
    incidents = [dict(r) for r in cursor.fetchall()]

    # 2. 15-talik nominal records
    cursor.execute("""
    SELECT sheet_name, row_index, cells_json
    FROM excel_15_talik_sheets
    WHERE is_header = 0 AND cells_json LIKE ?
    LIMIT 10
    """, (f"%{clean_fio}%",))
    records = []
    for r in cursor.fetchall():
        cells = json.loads(r['cells_json']) if r['cells_json'] else []
        records.append({
            "sheet_name": r['sheet_name'],
            "district_name": district or "Farg‘ona",
            "cells": cells
        })

    conn.close()
    
    return JSONResponse({
        "status": "success",
        "student_fio": clean_fio,
        "district": district,
        "incidents_count": len(incidents),
        "incidents": incidents,
        "nominal_records_count": len(records),
        "nominal_records": records
    })

@app.post("/api/ai/evaluate-report")
async def evaluate_report_endpoint(
    task_title: str = Form(...),
    district_name: str = Form(...),
    report_text: str = Form(...),
    file_name: str = Form("")
):
    evaluation = evaluate_district_report_ai(
        assignment_title=task_title,
        district_name=district_name,
        report_text=report_text,
        file_name=file_name
    )
    return JSONResponse({"status": "success", "evaluation": evaluation})

@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, month: int = 8, year: int = 2026):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    # Months list 1..12
    months_list = []
    for m in range(1, 13):
        months_list.append({
            'num': m,
            'name': MONTH_NAMES_UZ[m],
            'is_selected': (m == month),
            'status_badge': 'Yakunlangan' if m <= 8 else ('Faol' if m == 9 else 'Kutilmoqda')
        })

    # List generated export files
    files = []
    if os.path.exists(EXPORTS_DIR):
        for f in os.listdir(EXPORTS_DIR):
            p = os.path.join(EXPORTS_DIR, f)
            files.append({
                'name': f,
                'size': f"{os.path.getsize(p) / 1024:.1f} KB",
                'date': datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d %H:%M')
            })
    files.sort(key=lambda x: x['date'], reverse=True)

    return templates.TemplateResponse(request=request, name="reports.html", context={
        "current_user": user,
        "months": months_list,
        "selected_month": month,
        "selected_month_name": MONTH_NAMES_UZ.get(month, "Avgust"),
        "selected_year": year,
        "files": files
    })

# ==================== ACTIONS & APIS ====================

@app.post("/api/work-plans/add-item")
async def add_work_plan_item(
    plan_id: int = Form(...),
    section_number: int = Form(1),
    item_code: str = Form(...),
    task_description: str = Form(...),
    deadline_text: str = Form(""),
    responsible_persons: str = Form("")
):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO work_plan_items (
        plan_id, section_number, item_code, task_description,
        deadline_text, responsible_persons, status
    ) VALUES (?, ?, ?, ?, ?, ?, 'Kutilmoqda')
    """, (plan_id, section_number, item_code, task_description, deadline_text, responsible_persons))
    conn.commit()
    conn.close()
    return JSONResponse({"status": "success", "message": f"{item_code}-band muvaffaqiyatli qo‘shildi!"})

@app.post("/api/work-plans/update-item")
async def update_work_plan_item(
    item_id: int = Form(...),
    task_description: str = Form(...),
    deadline_text: str = Form(...),
    status: str = Form("Kutilmoqda")
):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE work_plan_items 
    SET task_description = ?, deadline_text = ?, status = ?
    WHERE id = ?
    """, (task_description, deadline_text, status, item_id))
    
    # Also update any linked district assignments
    cursor.execute("""
    UPDATE task_district_assignments
    SET assignment_instructions = ?, deadline_date = ?
    WHERE work_plan_item_id = ?
    """, (task_description, deadline_text, item_id))

    conn.commit()
    conn.close()
    return JSONResponse({"status": "success", "message": "Vazifa muvaffaqiyatli tahrirlandi va hududlar bilan sinxronlashtirildi!"})

@app.post("/api/work-plans/assign-territory")
async def assign_territory(
    work_plan_item_id: int = Form(...),
    district_id: str = Form("all"),
    instructions: str = Form(""),
    deadline_date: str = Form("2026-10-15")
):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT item_code, task_description FROM work_plan_items WHERE id = ?", (work_plan_item_id,))
    item = cursor.fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Vazifa topilmadi")

    inst = instructions if instructions else item['task_description']
    target_districts = []

    if district_id == "all":
        cursor.execute("SELECT id, name FROM districts ORDER BY sort_order")
        target_districts = cursor.fetchall()
        assigned_msg = "Barcha 19 ta tuman va shaharga"
    else:
        ids = [int(x.strip()) for x in district_id.split(",") if x.strip().isdigit()]
        if not ids:
            cursor.execute("SELECT id, name FROM districts ORDER BY sort_order")
            target_districts = cursor.fetchall()
            assigned_msg = "Barcha 19 ta tuman va shaharga"
        else:
            placeholders = ",".join(["?"] * len(ids))
            cursor.execute(f"SELECT id, name FROM districts WHERE id IN ({placeholders})", ids)
            target_districts = cursor.fetchall()
            assigned_msg = ", ".join([d['name'] for d in target_districts])

    count = 0
    for d in target_districts:
        title = f"{item['item_code']}-band o‘rganishi ({d['name']})"
        cursor.execute("""
        INSERT INTO task_district_assignments (
            work_plan_item_id, district_id, assigned_by_user_id,
            assignment_title, assignment_instructions, deadline_date, status
        ) VALUES (?, ?, 3, ?, ?, ?, 'Yangi')
        """, (work_plan_item_id, d['id'], title, inst, deadline_date))
        count += 1

    conn.commit()
    conn.close()
    return JSONResponse({
        "status": "success", 
        "message": f"{count} ta hududga ({assigned_msg}) o‘rganish vazifasi muvaffaqiyatli biriktirildi!"
    })

# ==================== HUDUDLARGA TOPSHIRIQ / TAQDIMNOMA / MUROJAAT YUBORISH ====================
@app.post("/api/admin/create-district-assignment")
async def create_district_assignment(
    request: Request,
    doc_type: str = Form("Topshiriq"),
    doc_number: str = Form(""),
    doc_date: str = Form(""),
    priority: str = Form("Oddiy"),
    assignment_title: str = Form(...),
    assignment_instructions: str = Form(""),
    deadline_date: str = Form(""),
    district_ids: str = Form("all"),
    attachment_file: UploadFile = File(None)
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Tizimga kirilmagan")
    if user.get("role") not in ["admin", "regional_head", "curator"]:
        raise HTTPException(status_code=403, detail="Vazifa biriktirish huquqi faqat boshqarma ma’murlariga berilgan")

    attachment_path = None
    if attachment_file and getattr(attachment_file, 'filename', None) and attachment_file.filename.strip():
        now_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_orig = sanitize_filename(os.path.basename(attachment_file.filename))
        saved_filename = f"{now_ts}_{safe_orig}"
        tasks_dir = os.path.join(STATIC_DIR, "uploads", "tasks")
        os.makedirs(tasks_dir, exist_ok=True)
        dest_full = os.path.join(tasks_dir, saved_filename)
        with open(dest_full, "wb") as bf:
            shutil.copyfileobj(attachment_file.file, bf)
        attachment_path = f"/static/uploads/tasks/{saved_filename}"

    conn = get_db()
    cursor = conn.cursor()

    if district_ids == "all" or not district_ids.strip():
        cursor.execute("SELECT id, name FROM districts ORDER BY sort_order")
        target_districts = cursor.fetchall()
        assigned_msg = "Barcha 19 ta tuman va shaharga"
    else:
        ids = [int(x.strip()) for x in district_ids.split(",") if x.strip().isdigit()]
        if not ids:
            cursor.execute("SELECT id, name FROM districts ORDER BY sort_order")
            target_districts = cursor.fetchall()
            assigned_msg = "Barcha 19 ta tuman va shaharga"
        else:
            placeholders = ",".join(["?"] * len(ids))
            cursor.execute(f"SELECT id, name FROM districts WHERE id IN ({placeholders})", ids)
            target_districts = cursor.fetchall()
            assigned_msg = ", ".join([d['name'] for d in target_districts])

    user_id = user.get("id", 1)
    user_fio = user.get("fio", "Boshqarma mas’uli")
    count = 0
    for d in target_districts:
        cursor.execute("""
        INSERT INTO task_district_assignments (
            district_id, assigned_by_user_id, doc_type, doc_number, doc_date,
            priority, assignment_title, assignment_instructions, attachment_path,
            deadline_date, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Yangi')
        """, (
            d['id'], user_id, doc_type, doc_number, doc_date,
            priority, assignment_title, assignment_instructions, attachment_path,
            deadline_date
        ))
        count += 1

    log_audit("Yangi topshiriq/taqdimnoma yuborildi", f"{doc_type} #{doc_number}: {assignment_title} -> {assigned_msg}", user_fio, user_id)

    conn.commit()
    conn.close()

    return JSONResponse({
        "status": "success",
        "message": f"{count} ta hududga ({assigned_msg}) '{doc_type}' hujjati muvaffaqiyatli yuborildi!",
        "count": count
    })

# ==================== HUDUD JAVOB XATI VA ASOSLARINI TOPSHIRISH ====================
@app.post("/api/district-assignments/submit-response")
@app.post("/api/district-assignments/submit-proof")
@app.post("/api/assignments/upload-proof")
async def submit_district_response(
    request: Request,
    assignment_id: int = Form(...),
    response_number: Optional[str] = Form(None),
    response_date: Optional[str] = Form(None),
    proof_text: Optional[str] = Form(""),
    comment: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    response_file: Optional[UploadFile] = File(None),
    proof_file: Optional[UploadFile] = File(None),
    proof_files: Optional[List[UploadFile]] = File(None),
    basis_files: Optional[List[UploadFile]] = File(None)
):
    user = get_current_user(request)
    submitted_by = user.get("fio") if user else "Tuman MMTB Mas’uli"

    # Merge proof_text / comment
    final_text = (proof_text or "").strip()
    if comment and comment.strip() and comment not in final_text:
        final_text = f"{final_text}\n{comment.strip()}".strip() if final_text else comment.strip()

    now_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    resp_dir = os.path.join(STATIC_DIR, "uploads", "responses")
    basis_dir = os.path.join(STATIC_DIR, "uploads", "responses", "basis")
    os.makedirs(resp_dir, exist_ok=True)
    os.makedirs(basis_dir, exist_ok=True)

    # 1. Main response letter file (PDF / Word)
    main_letter = response_file or proof_file
    response_letter_web_path = None
    all_files_for_local_passport = []

    if main_letter and getattr(main_letter, 'filename', None) and main_letter.filename.strip():
        safe_name = sanitize_filename(os.path.basename(main_letter.filename))
        dest_filename = f"{now_ts}_javob_{safe_name}"
        dest_path = os.path.join(resp_dir, dest_filename)
        with open(dest_path, "wb") as bf:
            shutil.copyfileobj(main_letter.file, bf)
        main_letter.file.seek(0)
        response_letter_web_path = f"/static/uploads/responses/{dest_filename}"
        all_files_for_local_passport.append(main_letter)

    # 2. Basis files (multiple attachments)
    basis_web_paths = []
    incoming_basis = []
    if basis_files:
        incoming_basis.extend([f for f in basis_files if f and getattr(f, 'filename', None) and f.filename.strip()])
    if proof_files:
        for f in proof_files:
            if f and getattr(f, 'filename', None) and f.filename.strip() and f != main_letter and f not in incoming_basis:
                incoming_basis.append(f)

    for idx, bf in enumerate(incoming_basis, 1):
        safe_name = sanitize_filename(os.path.basename(bf.filename))
        dest_filename = f"{now_ts}_asos_{idx}_{safe_name}"
        dest_path = os.path.join(basis_dir, dest_filename)
        with open(dest_path, "wb") as out:
            shutil.copyfileobj(bf.file, out)
        bf.file.seek(0)
        basis_web_paths.append(f"/static/uploads/responses/basis/{dest_filename}")
        all_files_for_local_passport.append(bf)

    # Local passport & windows storage (if available)
    folder_path = ""
    saved_files = []
    try:
        save_result = save_uploaded_files_and_passport(
            assignment_id=assignment_id,
            submitted_by=submitted_by,
            proof_text=final_text,
            files=all_files_for_local_passport
        )
        folder_path = save_result.get("folder_path", "")
        saved_files = save_result.get("saved_files", [])
    except Exception as e:
        print(f"[Storage Service Info] {e}")

    # Combine all attachments
    all_attachments = []
    if response_letter_web_path:
        all_attachments.append(response_letter_web_path)
    all_attachments.extend(basis_web_paths)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO execution_proofs (
        target_type, target_id, submitted_by_user_id, submitted_by_fio,
        proof_text, response_letter_number, response_letter_date,
        response_letter_path, basis_attachments, attachment_paths, approval_status
    ) VALUES ('task_district_assignment', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Kutilmoqda')
    """, (
        assignment_id, user.get("id") if user else None, submitted_by,
        final_text, response_number or "", response_date or datetime.now().strftime("%Y-%m-%d"),
        response_letter_web_path or "", json.dumps(basis_web_paths), json.dumps(all_attachments)
    ))

    cursor.execute("UPDATE task_district_assignments SET status = 'Hisobot topshirildi' WHERE id = ?", (assignment_id,))

    # Agar ushbu band bo'yicha barcha hududlar topshirgan bo'lsa, band statusini avtomatik 'Bajarildi' qilish
    cursor.execute("SELECT work_plan_item_id FROM task_district_assignments WHERE id = ?", (assignment_id,))
    wpi_row = cursor.fetchone()
    if wpi_row and wpi_row['work_plan_item_id']:
        wpi_id = wpi_row['work_plan_item_id']
        cursor.execute("""
        SELECT COUNT(*) as total, 
               SUM(CASE WHEN status IN ('Hisobot topshirildi', 'Tasdiqlandi') THEN 1 ELSE 0 END) as submitted 
        FROM task_district_assignments 
        WHERE work_plan_item_id = ?
        """, (wpi_id,))
        stats = cursor.fetchone()
        if stats and stats['total'] > 0 and stats['total'] == stats['submitted']:
            cursor.execute("UPDATE work_plan_items SET status = 'Bajarildi' WHERE id = ?", (wpi_id,))

    conn.commit()
    conn.close()

    return JSONResponse({
        "status": "success", 
        "message": "Rasmiy javob xati va asoslovchi hujjatlar muvaffaqiyatli qabul qilindi!",
        "response_letter_path": response_letter_web_path,
        "basis_count": len(basis_web_paths),
        "folder_path": folder_path,
        "saved_files": saved_files
    })

# ==================== BOSHQARMA TOMONIDAN IJRONI TEKSHIRISH / TASDIQLASH ====================
@app.post("/api/district-assignments/review-status")
async def review_district_assignment(
    request: Request,
    assignment_id: int = Form(...),
    proof_id: Optional[int] = Form(None),
    status: str = Form(...), # "Tasdiqlandi" or "Qaytarildi"
    rejection_reason: Optional[str] = Form("")
):
    user = get_current_user(request)
    if not user or user.get("role") not in ["admin", "regional_head", "curator"]:
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE task_district_assignments SET status = ? WHERE id = ?", (status, assignment_id))

    if proof_id:
        cursor.execute("""
        UPDATE execution_proofs 
        SET approval_status = ?, rejection_reason = ?, approved_by_user_id = ?
        WHERE id = ?
        """, (status, rejection_reason or "", user.get("id"), proof_id))
    else:
        cursor.execute("""
        UPDATE execution_proofs 
        SET approval_status = ?, rejection_reason = ?, approved_by_user_id = ?
        WHERE target_type = 'task_district_assignment' AND target_id = ?
        ORDER BY id DESC LIMIT 1
        """, (status, rejection_reason or "", user.get("id"), assignment_id))

    conn.commit()
    conn.close()
    return JSONResponse({"status": "success", "message": f"Topshiriq holati '{status}' deb belgilandi!"})

# Windows Explorer orqali papkani ochish API
@app.post("/api/system/open-folder")
async def open_system_folder(folder_path: str = Form(None), assignment_id: int = Form(None)):
    target_path = folder_path
    if not target_path and assignment_id:
        info = get_assignment_storage_path(assignment_id)
        target_path = info["folder_path"]

    if not target_path:
        target_path = BASE_STORAGE_DIR

    success = open_folder_in_windows_explorer(target_path)
    if success:
        return JSONResponse({"status": "success", "message": f"Papka kompyuterda ochildi: {target_path}", "path": target_path})
    else:
        return JSONResponse({"status": "error", "message": "Papkani ochib bo'lmadi", "path": target_path}, status_code=500)

# Ish rejalari tahliliy Excel generatsiyasi
@app.post("/api/reports/generate-plan-excel")
async def trigger_plan_excel(year: int = Form(2026)):
    fname, fpath = generate_plan_analytical_excel(year=year)
    return JSONResponse({"status": "success", "filename": fname, "download_url": f"/exports/{fname}"})

# Report Generation APIs with Month & Year parameters
@app.post("/api/reports/generate-word")
async def trigger_word_report(month: int = Form(8), year: int = 2026):
    fname, fpath = generate_crime_analytical_word(month_num=month, year=year)
    return JSONResponse({"status": "success", "filename": fname, "download_url": f"/exports/{fname}"})

@app.post("/api/reports/generate-excel")
async def trigger_excel_report(month: int = Form(8), year: int = 2026):
    fname, fpath = generate_15_talik_excel(month_num=month, year=year)
    return JSONResponse({"status": "success", "filename": fname, "download_url": f"/exports/{fname}"})

@app.post("/api/reports/generate-incidents")
async def trigger_incidents_report(month: int = Form(8), year: int = 2026):
    fname, fpath = generate_incidents_excel(month_num=month, year=year)
    return JSONResponse({"status": "success", "filename": fname, "download_url": f"/exports/{fname}"})

@app.post("/api/reports/generate-rating")
async def trigger_rating_report(month: int = Form(8), year: int = 2026):
    fname, fpath = generate_discipline_rating(month_num=month, year=year)
    return JSONResponse({"status": "success", "filename": fname, "download_url": f"/exports/{fname}"})

@app.get("/exports/{filename}")
async def download_export(filename: str):
    fpath = os.path.join(EXPORTS_DIR, filename)
    if os.path.exists(fpath):
        return FileResponse(fpath, filename=filename)
    raise HTTPException(status_code=404, detail="Fayl topilmadi")

# ==================== ADMIN CONVENIENCE APIS ====================

@app.get("/api/search")
async def global_search(q: str = ""):
    q = q.strip()
    if not q or len(q) < 2:
        return JSONResponse({"status": "success", "results": []})
    
    conn = get_db()
    cursor = conn.cursor()
    results = []
    
    # 1. Districts
    cursor.execute("SELECT id, name, code, is_city FROM districts WHERE name LIKE ? OR code LIKE ? LIMIT 5", (f"%{q}%", f"%{q}%"))
    for d in cursor.fetchall():
        results.append({
            "type": "district",
            "badge": "🏢 Hudud",
            "title": d['name'],
            "subtitle": f"Kodi: {d['code']} | {'Shahar' if d['is_city'] else 'Tuman'}",
            "url": f"/?district_id={d['id']}",
            "action_id": d['id']
        })
        
    # 2. Juvenile incidents
    cursor.execute("""
    SELECT id, student_fio, school_name, criminal_article, days_remaining, status 
    FROM juvenile_incidents 
    WHERE student_fio LIKE ? OR school_name LIKE ? OR criminal_article LIKE ? OR incident_details LIKE ?
    LIMIT 6
    """, (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"))
    for inc in cursor.fetchall():
        results.append({
            "type": "incident",
            "badge": "🚨 10-kunlik Nazorat",
            "title": inc['student_fio'],
            "subtitle": f"{inc['school_name']} | Modda: {inc['criminal_article']} | {inc['days_remaining']} kun qoldi",
            "url": f"/incidents?search={inc['student_fio']}",
            "action_id": inc['id']
        })
        
    # 3. Work plan items
    cursor.execute("""
    SELECT id, item_code, task_description, deadline_text, responsible_persons, status 
    FROM work_plan_items 
    WHERE item_code LIKE ? OR task_description LIKE ? OR responsible_persons LIKE ?
    LIMIT 6
    """, (f"%{q}%", f"%{q}%", f"%{q}%"))
    for item in cursor.fetchall():
        desc = item['task_description'][:90] + ("..." if len(item['task_description']) > 90 else "")
        results.append({
            "type": "task",
            "badge": "📋 Ish rejasi",
            "title": f"{item['item_code']}-band: {desc}",
            "subtitle": f"Mas’ul: {item['responsible_persons']} | Muddat: {item['deadline_text'] or 'Doimiy'}",
            "url": f"/work-plans?search={item['item_code']}",
            "action_id": item['id']
        })

    # 4. Schools
    cursor.execute("SELECT s.id, s.name, s.school_number, d.name as dname FROM schools s JOIN districts d ON s.district_id = d.id WHERE s.name LIKE ? OR s.school_number LIKE ? LIMIT 4", (f"%{q}%", f"%{q}%"))
    for s in cursor.fetchall():
        results.append({
            "type": "school",
            "badge": "🏫 Maktab",
            "title": f"{s['school_number']}-maktab ({s['dname']})",
            "subtitle": s['name'],
            "url": f"/incidents?search={s['school_number']}",
            "action_id": s['id']
        })

    conn.close()
    return JSONResponse({"status": "success", "results": results})

@app.get("/api/districts/{district_id}/dossier")
async def get_district_dossier(district_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM districts WHERE id = ?", (district_id,))
    dist = cursor.fetchone()
    if not dist:
        conn.close()
        raise HTTPException(status_code=404, detail="Tuman topilmadi")

    cursor.execute("SELECT COUNT(*) as cnt FROM schools WHERE district_id = ?", (district_id,))
    school_cnt = cursor.fetchone()['cnt']
    if school_cnt == 0:
        school_cnt = 54 if not dist['is_city'] else 41

    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN days_remaining <= 3 AND status='Nazoratda' THEN 1 ELSE 0 END) as urgent FROM juvenile_incidents WHERE district_id = ?", (district_id,))
    inc_row = cursor.fetchone()
    incident_cnt = inc_row['total'] or 0
    urgent_cnt = inc_row['urgent'] or 0

    cursor.execute("""
    SELECT id, student_fio, school_name, criminal_article, incident_date, days_remaining, status 
    FROM juvenile_incidents 
    WHERE district_id = ? 
    ORDER BY days_remaining ASC LIMIT 5
    """, (district_id,))
    recent_incidents = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT id, assignment_title, deadline_date, status 
    FROM task_district_assignments 
    WHERE district_id = ? 
    ORDER BY id DESC LIMIT 5
    """, (district_id,))
    assignments = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT numeric_values FROM monthly_15_records r
    JOIN monthly_15_submissions s ON r.submission_id = s.id
    WHERE s.district_id = ? AND r.direction_number = 10 LIMIT 1
    """, (district_id,))
    c_row = cursor.fetchone()
    crime_vals = json.loads(c_row['numeric_values']) if c_row and c_row['numeric_values'] else {}

    j25 = crime_vals.get('jinoyat_2025', 0)
    j26 = crime_vals.get('jinoyat_2026', 0)
    diff = crime_vals.get('farqi', j26 - j25)

    risk_level = "Yuqori (Qizil hudud)" if diff > 0 or urgent_cnt > 0 else ("O‘rtacha (Sariq hudud)" if diff == 0 else "Namunali (Yashil hudud)")
    risk_color = "red" if diff > 0 or urgent_cnt > 0 else ("amber" if diff == 0 else "emerald")

    conn.close()

    return JSONResponse({
        "status": "success",
        "district": {
            "id": dist['id'],
            "name": dist['name'],
            "code": dist['code'],
            "is_city": dist['is_city'],
            "schools_count": school_cnt,
            "incident_count": incident_cnt,
            "urgent_incidents": urgent_cnt,
            "crime_2025": j25,
            "crime_2026": j26,
            "crime_diff": diff,
            "risk_level": risk_level,
            "risk_color": risk_color,
            "recent_incidents": recent_incidents,
            "assignments": assignments
        }
    })

@app.get("/api/admin/backup")
async def create_backup():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"fargona_mmtb_backup_{timestamp}.zip"
    zip_path = os.path.join(EXPORTS_DIR, zip_filename)
    
    db_file = os.path.join(CURRENT_DIR, "data", "monitoring.db")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        if os.path.exists(db_file):
            zipf.write(db_file, arcname="data/monitoring.db")
        if os.path.exists(UPLOADS_DIR):
            for root, dirs, files in os.walk(UPLOADS_DIR):
                for file in files:
                    file_p = os.path.join(root, file)
                    arc_p = os.path.relpath(file_p, CURRENT_DIR)
                    zipf.write(file_p, arcname=arc_p)
                    
    log_audit("Tizim Zaxirasi", f"Admin tomonidan zaxira nusxa (.zip) olindi: {zip_filename}")
    return FileResponse(zip_path, filename=zip_filename, media_type="application/zip")

@app.post("/api/admin/import-excel-15")
async def import_excel_15_file(file: UploadFile = File(...)):
    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        raise HTTPException(status_code=400, detail="Faqat Excel (.xlsx, .xls) fayli qabul qilinadi")
    
    temp_path = os.path.join(UPLOADS_DIR, f"imported_15talik_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    success, msg = reload_15_talik_from_file(temp_path)
    if not success:
        raise HTTPException(status_code=500, detail=msg)
        
    log_audit("15-talik Excel Yangilandi", f"Yangi 15-talik Excel fayli yuklandi: {file.filename}")
    return JSONResponse({"status": "success", "message": msg})

@app.post("/api/admin/import-word-plan")
async def import_word_plan_file(
    file: UploadFile = File(...), 
    owner_name: str = Form("A.Azimov"),
    replace_old: bool = Form(True)
):
    if not (file.filename.endswith('.docx') or file.filename.endswith('.doc')):
        raise HTTPException(status_code=400, detail="Faqat Word (.docx) fayli qabul qilinadi")

    temp_path = os.path.join(UPLOADS_DIR, f"imported_plan_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        count = parse_and_import_work_plan(temp_path, owner_name, "Mas’ul xodim", replace_existing=replace_old)
        mode_text = "eski reja arxivlanib, yangisi o‘rnatildi" if replace_old else "yangi reja sifatida qo‘shildi"
        log_audit("Ish rejasi yangilandi", f"{owner_name} ish rejasi Word fayldan yangilandi ({mode_text}, {count} ta band)")
        return JSONResponse({
            "status": "success", 
            "message": f"{owner_name} ish rejasi muvaffaqiyatli qabul qilindi! ({mode_text}, jami {count} ta band tumanlarga taqsimlandi)."
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Xatolik: {str(e)}")

@app.get("/admin/audit", response_class=HTMLResponse)
async def audit_log_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.get("role") == "district":
        return RedirectResponse(url="/district-portal", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100")
    logs = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(request=request, name="audit_log.html", context={"current_user": user, "logs": logs})

@app.get("/reports/print-summary", response_class=HTMLResponse)
async def print_summary_page(request: Request, month: int = 8, year: int = 2026):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT d.id, d.name, d.code, d.is_city,
           (SELECT COUNT(*) FROM juvenile_incidents WHERE district_id = d.id) as inc_cnt,
           (SELECT COUNT(*) FROM task_district_assignments WHERE district_id = d.id AND status = 'Bajarildi') as done_tasks,
           (SELECT COUNT(*) FROM task_district_assignments WHERE district_id = d.id) as total_tasks,
           (SELECT numeric_values FROM monthly_15_records r 
            JOIN monthly_15_submissions s ON r.submission_id = s.id 
            WHERE s.district_id = d.id AND r.direction_number = 10 LIMIT 1) as crime_data
    FROM districts d
    ORDER BY d.sort_order
    """)
    districts = cursor.fetchall()
    
    dist_list = []
    for d in districts:
        c_data = json.loads(d['crime_data']) if d['crime_data'] else {}
        j25 = c_data.get('jinoyat_2025', 0)
        j26 = c_data.get('jinoyat_2026', 0)
        diff = c_data.get('farqi', j26 - j25)
        score = 90 - (j26 * 2) + (10 if diff <= 0 else -10)
        score = max(50, min(100, score))
        dist_list.append({
            "name": d['name'],
            "code": d['code'],
            "is_city": d['is_city'],
            "j25": j25,
            "j26": j26,
            "diff": diff,
            "done_tasks": d['done_tasks'],
            "total_tasks": d['total_tasks'],
            "score": score
        })
    
    dist_list.sort(key=lambda x: x['score'], reverse=True)
    for i, d in enumerate(dist_list, 1):
        d['rank'] = i
        
    month_name = MONTH_NAMES_UZ.get(month, "Avgust")
    conn.close()
    return templates.TemplateResponse(request=request, name="print_summary.html", context={
        "month_num": month,
        "month_name": month_name,
        "year": year,
        "districts": dist_list
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
