# -*- coding: utf-8 -*-
import os
import sys
import json
import asyncio
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import get_db, log_audit

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8919524994:AAEznkJcRvj1pnrqnwW6IvPSB5A5cIZ77hQ")
UPLOADS_BOT_DIR = os.path.join(PROJECT_ROOT, "static", "uploads", "bot_reports")
os.makedirs(UPLOADS_BOT_DIR, exist_ok=True)

try:
    from aiogram import Bot, Dispatcher, types, F
    from aiogram.filters import Command
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    AIOGRAM_AVAILABLE = True
except ImportError:
    AIOGRAM_AVAILABLE = False

class ReportSubmissionState(StatesGroup):
    waiting_for_report = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

def get_main_keyboard(is_admin=False):
    buttons = [
        [KeyboardButton(text="📌 Mening vazifalarim"), KeyboardButton(text="🏢 Kelib tushgan o‘rganishlar")],
        [KeyboardButton(text="📊 15-talik monitoring"), KeyboardButton(text="🚨 10-kunlik nazorat (Hodisalar)")],
        [KeyboardButton(text="📤 Hisobot topshirish"), KeyboardButton(text="👤 Profil va Sozlamalar")]
    ]
    if is_admin:
        buttons.insert(0, [KeyboardButton(text="⚙️ Admin Boshqaruv Markazi"), KeyboardButton(text="📢 Ommaviy Xabarnoma")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_admin_inline_markup():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Ommaviy Xabar (19 tuman)", callback_data="btn_admin_broadcast"),
            InlineKeyboardButton(text="🌅 Tonggi Xulosa (Digest)", callback_data="btn_admin_digest")
        ],
        [
            InlineKeyboardButton(text="🚨 10-kunlik Shoshilinch", callback_data="btn_admin_incidents"),
            InlineKeyboardButton(text="📊 15-talik Holati", callback_data="btn_admin_15")
        ],
        [
            InlineKeyboardButton(text="🔄 Yangilash", callback_data="btn_admin_refresh")
        ]
    ])

def check_user_access(chat_id: int):
    """
    Checks if chat_id has authorized access to the closed bot.
    Returns (is_authorized: bool, is_admin: bool, user_info: dict)
    """
    admin_env_str = os.getenv("ADMIN_TELEGRAM_IDS", "")
    admin_env_ids = [s.strip() for s in admin_env_str.split(",") if s.strip()]
    if str(chat_id) in admin_env_ids or chat_id in [447337688, 752608266, 5957838266, 8328891135]:
        return True, True, {'role': 'admin', 'fio': 'Bosh Administrator', 'is_approved': 1}

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_chat_id = ?", (str(chat_id),))
    row = cursor.fetchone()
    conn.close()

    if row and row['is_approved'] == 1:
        is_admin = (row['role'] == 'admin')
        return True, is_admin, dict(row)

    return False, False, None

def get_all_recipient_chat_ids():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_chat_id FROM users WHERE telegram_chat_id IS NOT NULL AND telegram_chat_id != '' AND is_approved = 1")
    rows = cursor.fetchall()
    conn.close()
    return list({r['telegram_chat_id'] for r in rows})

def get_admin_chat_ids():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_chat_id FROM users WHERE role = 'admin' AND telegram_chat_id IS NOT NULL AND is_approved = 1")
    rows = cursor.fetchall()
    conn.close()
    cids = list({r['telegram_chat_id'] for r in rows})
    # Add env admin ids
    admin_env_str = os.getenv("ADMIN_TELEGRAM_IDS", "")
    for s in admin_env_str.split(","):
        if s.strip() and s.strip() not in cids:
            cids.append(s.strip())
    for s in [447337688, 752608266, 5957838266, 8328891135]:
        if str(s) not in cids:
            cids.append(str(s))
    return cids

async def generate_digest_text():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status='Bajarildi' THEN 1 ELSE 0 END) as done FROM work_plan_items")
    wp = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status='Yangi' THEN 1 ELSE 0 END) as new_cnt FROM task_district_assignments")
    dist_tasks = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) as active, SUM(CASE WHEN days_remaining <= 3 THEN 1 ELSE 0 END) as urgent FROM juvenile_incidents WHERE status='Nazoratda'")
    inc = cursor.fetchone()

    cursor.execute("SELECT COUNT(DISTINCT district_id) as submitted FROM monthly_15_submissions WHERE year=2026 AND month=8")
    m15 = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) as pending FROM execution_proofs WHERE approval_status = 'Kutilmoqda'")
    proofs = cursor.fetchone()

    conn.close()

    text = (
        "🌅 <b>FARG‘ONA VILOYATI MMTB — TEZKOR KUNLIK XULOSA (DIGEST)</b>\n"
        f"📅 Sana: <b>{datetime.now().strftime('%d.%m.%Y %H:%M')}</b>\n"
        "────────────────────────────\n"
        f"📋 <b>Ish rejalari ijrosi:</b>\n"
        f"   • Jami: {wp['total']} ta | Bajarildi: 🟢 {wp['done'] or 0} ta\n\n"
        f"🏢 <b>Hududlarga yuklatilgan topshiriqlar:</b>\n"
        f"   • Jami: {dist_tasks['total']} ta | Yangi o‘rganishlar: 🟡 {dist_tasks['new_cnt'] or 0} ta\n\n"
        f"🚨 <b>10-kunlik nazoratdagi favqulodda holatlar:</b>\n"
        f"   • Nazoratda: {inc['active']} ta\n"
        f"   • ⚠️ <b>3 kun va kam qolgan shoshilinch: {inc['urgent'] or 0} ta</b>\n\n"
        f"📊 <b>Oylik '15-talik' hisoboti:</b>\n"
        f"   • Avgust oyi qabul: 🟢 {m15['submitted'] or 0} / 19 ta (100%)\n\n"
        f"📥 <b>Kutilayotgan tasdiqlar:</b>\n"
        f"   • Admin tasdig‘ini kutayotgan hisobotlar: <b>{proofs['pending'] or 0} ta</b>\n"
        "────────────────────────────\n"
        "<i>Tizim nazorati avtomatik tarzda 24/7 rejimida olib borilmoqda.</i>"
    )
    return text

async def start_bot():
    if not AIOGRAM_AVAILABLE or not BOT_TOKEN:
        print("[Telegram Bot] Bot token not provided or aiogram not configured.")
        return

    print(f"[Telegram Bot] Initializing bot with token: {BOT_TOKEN[:10]}...")
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # --- COMMAND /start ---
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        chat_id = message.from_user.id
        username = message.from_user.username or ""
        full_name = message.from_user.full_name

        is_auth, is_admin, u_info = check_user_access(chat_id)
        if not is_auth:
            text = (
                "⛔️ <b>KIRISH CHEKLANGAN! (XAVFSIZLIK NAZORATI)</b>\n\n"
                "🏛 <b>Farg‘ona viloyati Maktabgacha va maktab ta’limi boshqarmasi</b>\n"
                "Ijro intizomi va profilaktika monitoringi maxsus idoraviy yopiq tizimi.\n\n"
                f"Hurmatli <b>{full_name}</b>, sizning hisobingiz (Telegram ID: <code>{chat_id}</code>) tizimda tasdiqlanmagan.\n\n"
                "<i>Xizmat axborotlari maxfiyligini ta’minlash maqsadida ushbu botdan faqat viloyat boshqarmasi va tuman/shahar MMTB mas’ul xodimlari foydalanishi mumkin.</i>\n\n"
                "Agar siz boshqarma yoki tuman mas’uli bo‘lsangiz, quyidagi tugma orqali administratorga kirish so‘rovi yuborishingiz mumkin:"
            )
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📩 Boshqarmadan ruxsat so‘rash", callback_data=f"req_access_{chat_id}")]
            ])
            await message.answer(text, parse_mode="HTML", reply_markup=markup)
            return

        welcome_text = (
            f"Assalomu alaykum, <b>{full_name}</b>!\n\n"
            "🏛 <b>Farg‘ona viloyati Maktabgacha va maktab ta’limi boshqarmasi</b>\n"
            "Ijro nazorati va monitoring axborot tizimining rasmiy botiga xush kelibsiz.\n\n"
            "Ushbu bot orqali siz:\n"
            "• Shaxsiy ish rejalaringiz ijrosini nazorat qilishingiz;\n"
            "• Tuman va maktabingizga tushgan o‘rganish vazifalarini ko‘rishingiz;\n"
            "• Oylik '15-talik' monitoring ko‘rsatkichlarini kuzatishingiz;\n"
            "• Topshiriqlar bo‘yicha hisobot va fayllarni yuklashingiz;\n"
            "• Administrator buyruqlari va ko‘rsatmalarini qabul qilishingiz mumkin."
        )
        if is_admin:
            welcome_text += "\n\n⭐️ <i>Sizda Administratorlik huquqlari faollashtirilgan!</i>"

        await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard(is_admin=is_admin))

    # --- COMMAND /admin ---
    @dp.message(Command("admin"))
    @dp.message(F.text == "⚙️ Admin Boshqaruv Markazi")
    async def cmd_admin(message: types.Message):
        is_auth, is_admin, _ = check_user_access(message.from_user.id)
        if not is_admin:
            await message.answer("❌ Ushbu bo‘lim faqat Bosh Administrator uchun mo‘ljallangan.")
            return

        text = await generate_digest_text()
        await message.answer(
            f"👑 <b>ADMINISTRATOR BOSHQARUV PANELI</b>\n\n{text}",
            parse_mode="HTML",
            reply_markup=get_admin_inline_markup()
        )

    # --- COMMAND /digest ---
    @dp.message(Command("digest"))
    async def cmd_digest(message: types.Message):
        is_auth, _, _ = check_user_access(message.from_user.id)
        if not is_auth:
            await message.answer("⛔️ Kirish cheklangan.")
            return
        text = await generate_digest_text()
        await message.answer(text, parse_mode="HTML")

    # --- COMMAND /broadcast & Button ---
    @dp.message(Command("broadcast"))
    @dp.message(F.text == "📢 Ommaviy Xabarnoma")
    async def cmd_broadcast_prompt(message: types.Message, state: FSMContext):
        is_auth, is_admin, _ = check_user_access(message.from_user.id)
        if not is_admin:
            await message.answer("❌ Ommaviy xabarnoma yuborish faqat Bosh Administratorga ruxsat etilgan.")
            return
        
        args = message.text.replace("/broadcast", "").strip() if message.text and message.text.startswith("/broadcast") else ""
        if args:
            await execute_broadcast(bot, message, args)
        else:
            await state.set_state(BroadcastState.waiting_for_message)
            await message.answer(
                "📢 <b>19 ta tuman/shahar mas’ullariga ommaviy xabar yuborish</b>\n\n"
                "Iltimos, barcha tumanlarga yetkazilishi kerak bo‘lgan ko‘rsatma yoki rasmiy xabar matnini yuboring.\n"
                "<i>(Bekor qilish uchun /cancel deb yozing)</i>",
                parse_mode="HTML"
            )

    @dp.message(BroadcastState.waiting_for_message)
    async def process_broadcast_message(message: types.Message, state: FSMContext):
        if message.text and message.text.strip().lower() == "/cancel":
            await state.clear()
            await message.answer("❌ Ommaviy xabar yuborish bekor qilindi.", reply_markup=get_main_keyboard(True))
            return

        text = message.text or message.caption or "Rasmiy bildirishnoma"
        await state.clear()
        await execute_broadcast(bot, message, text)

    async def execute_broadcast(bot_inst, message, text_content):
        recipients = get_all_recipient_chat_ids()
        # Add current user to recipients if not there
        if str(message.from_user.id) not in recipients:
            recipients.append(str(message.from_user.id))

        success_count = 0
        fail_count = 0

        broadcast_body = (
            "🏛 <b>FARG‘ONA VILOYATI MMTB | RASMIY TEZKOR KO‘RSATMA</b>\n"
            f"📅 Sana: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"👤 Yuboruvchi: {message.from_user.full_name} (Boshqarma)\n"
            "────────────────────────────\n\n"
            f"{text_content}\n\n"
            "────────────────────────────\n"
            "<i>Ushbu ko‘rsatma barcha 19 ta tuman/shahar MMTB mas’ullariga yetkazildi. Ijrosi qat’iy nazoratda!</i>"
        )

        status_msg = await message.answer(f"⏳ Xabar tarqatilmoqda... (Jami: {len(recipients)} ta manzil)")

        for cid in recipients:
            try:
                await bot_inst.send_message(chat_id=cid, text=broadcast_body, parse_mode="HTML")
                success_count += 1
            except Exception:
                fail_count += 1

        log_audit(
            action="Telegram Broadcast",
            details=f"Ommaviy xabarnoma yuborildi: {text_content[:80]}... (Yetkazildi: {success_count}, Xato: {fail_count})",
            user_fio=message.from_user.full_name
        )

        await status_msg.edit_text(
            f"✅ <b>Ommaviy xabar muvaffaqiyatli tarqatildi!</b>\n\n"
            f"• Muvaffaqiyatli yetkazildi: <b>{success_count} ta</b>\n"
            f"• Yetkazilmadi: {fail_count} ta\n\n"
            f"<i>Barcha hudud mas’ullari zudlik bilan xabardor qilindi.</i>",
            parse_mode="HTML"
        )

    # --- INLINE CALLBACKS ---
    @dp.callback_query(F.data.startswith("btn_admin_"))
    async def handle_admin_buttons(callback: types.CallbackQuery, state: FSMContext):
        data = callback.data
        if data == "btn_admin_refresh":
            text = await generate_digest_text()
            await callback.message.edit_text(
                f"👑 <b>ADMINISTRATOR BOSHQARUV PANELI (Yangilandi)</b>\n\n{text}",
                parse_mode="HTML",
                reply_markup=get_admin_inline_markup()
            )
            await callback.answer("Yangilandi!")
        elif data == "btn_admin_digest":
            text = await generate_digest_text()
            await callback.message.answer(text, parse_mode="HTML")
            await callback.answer()
        elif data == "btn_admin_broadcast":
            await state.set_state(BroadcastState.waiting_for_message)
            await callback.message.answer(
                "📢 Barcha tumanlarga yuboriladigan xabar matnini kiriting:",
                parse_mode="HTML"
            )
            await callback.answer()
        elif data == "btn_admin_incidents":
            await show_incidents_summary(callback.message)
            await callback.answer()
        elif data == "btn_admin_15":
            await show_15_talik_summary(callback.message)
            await callback.answer()

    # --- INLINE APPROVAL / REJECTION OF SUBMISSIONS ---
    @dp.callback_query(F.data.startswith("approve_proof_"))
    async def handle_approve_proof(callback: types.CallbackQuery):
        proof_id = int(callback.data.replace("approve_proof_", ""))
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT submitted_by_fio, submitted_by_user_id, target_id FROM execution_proofs WHERE id = ?", (proof_id,))
        proof = cursor.fetchone()
        
        cursor.execute("UPDATE execution_proofs SET approval_status = 'Tasdiqlandi' WHERE id = ?", (proof_id,))
        if proof and proof['target_id']:
            cursor.execute("UPDATE task_district_assignments SET status = 'Bajarildi' WHERE id = ?", (proof['target_id'],))
        conn.commit()
        conn.close()

        log_audit(
            action="Tasdiqlash",
            details=f"Hisobot #{proof_id} Telegram orqali tasdiqlandi.",
            user_fio=callback.from_user.full_name
        )

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(
            f"✅ <b>Hisobot #{proof_id} TASDIQLANDI!</b>\n"
            f"Ijrochi: {proof['submitted_by_fio'] if proof else 'Mas’ul'}\n"
            f"Tasdiqladi: {callback.from_user.full_name}",
            parse_mode="HTML"
        )
        await callback.answer("Hisobot tasdiqlandi!")

    @dp.callback_query(F.data.startswith("reject_proof_"))
    async def handle_reject_proof(callback: types.CallbackQuery):
        proof_id = int(callback.data.replace("reject_proof_", ""))
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT submitted_by_fio FROM execution_proofs WHERE id = ?", (proof_id,))
        proof = cursor.fetchone()
        
        cursor.execute("UPDATE execution_proofs SET approval_status = 'Qaytarildi' WHERE id = ?", (proof_id,))
        conn.commit()
        conn.close()

        log_audit(
            action="Qaytarish",
            details=f"Hisobot #{proof_id} Telegram orqali kamchilik sababli qaytarildi.",
            user_fio=callback.from_user.full_name
        )

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(
            f"⚠️ <b>Hisobot #{proof_id} QAYTARILDI!</b>\n"
            f"Ijrochi: {proof['submitted_by_fio'] if proof else 'Mas’ul'}\n"
            f"Qaytargan: {callback.from_user.full_name}\n"
            "Ijrochiga qayta topshirish talabi yuborildi.",
            parse_mode="HTML"
        )
        await callback.answer("Hisobot qaytarildi!")

    # --- INLINE ACCESS APPROVAL CALLBACKS ---
    @dp.callback_query(F.data.startswith("req_access_"))
    async def handle_request_access(callback: types.CallbackQuery):
        chat_id = callback.from_user.id
        fio = callback.from_user.full_name
        uname = callback.from_user.username or ""

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, is_approved FROM users WHERE telegram_chat_id = ?", (str(chat_id),))
        row = cursor.fetchone()
        if not row:
            cursor.execute("""
            INSERT INTO users (username, password_hash, fio, role, telegram_chat_id, telegram_username, is_approved)
            VALUES (?, 'tg_pending', ?, 'curator', ?, ?, 0)
            """, (f"tg_{chat_id}", fio, str(chat_id), uname))
            conn.commit()
        conn.close()

        await callback.message.edit_text(
            f"⏳ <b>Ruxsat so‘rovingiz qabul qilindi!</b>\n\n"
            f"F.I.Sh: <b>{fio}</b>\nTelegram ID: <code>{chat_id}</code>\n\n"
            "<i>So‘rov Boshqarma administratoriga yuborildi. Ruxsat berilishi bilan ushbu botda xabarnoma olasiz.</i>",
            parse_mode="HTML"
        )

        admin_cids = get_admin_chat_ids()
        admin_markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ruxsat berish (Kurator)", callback_data=f"grant_acc_curator_{chat_id}"),
                InlineKeyboardButton(text="🏢 Tuman mas’uli", callback_data=f"grant_acc_district_{chat_id}")
            ],
            [
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"deny_acc_{chat_id}")
            ]
        ])
        for acid in admin_cids:
            try:
                await bot.send_message(
                    chat_id=int(acid),
                    text=f"🔔 <b>YANGI XODIM BOTGA KIRISH RUXSATINI SO‘RAMOQDA:</b>\n\n"
                         f"👤 F.I.Sh: <b>{fio}</b>\n"
                         f"🔗 Username: @{uname or 'mavjud emas'}\n"
                         f"🆔 Telegram ID: <code>{chat_id}</code>\n\n"
                         "Ushbu xodimga botdan foydalanish huquqini berasizmi?",
                    parse_mode="HTML",
                    reply_markup=admin_markup
                )
            except Exception:
                pass
        await callback.answer("So‘rov yuborildi!")

    @dp.callback_query(F.data.startswith("grant_acc_"))
    async def handle_grant_access(callback: types.CallbackQuery):
        parts = callback.data.split("_")
        role = parts[2]
        target_cid = parts[3]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_approved = 1, role = ? WHERE telegram_chat_id = ?", (role, target_cid))
        conn.commit()
        conn.close()

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"✅ Foydalanuvchiga ({target_cid}) <b>{role}</b> maqomi bilan ruxsat berildi!", parse_mode="HTML")

        try:
            await bot.send_message(
                chat_id=int(target_cid),
                text="🎉 <b>Tabriklaymiz! Boshqarma administratori sizga botdan foydalanish huquqini berdi.</b>\n\n"
                     "/start buyrug‘ini bosib boshqaruv menyusidan to‘liq foydalanishingiz mumkin.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard(is_admin=False)
            )
        except Exception:
            pass
        await callback.answer("Ruxsat berildi!")

    @dp.callback_query(F.data.startswith("deny_acc_"))
    async def handle_deny_access(callback: types.CallbackQuery):
        target_cid = callback.data.replace("deny_acc_", "")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE telegram_chat_id = ? AND is_approved = 0", (target_cid,))
        conn.commit()
        conn.close()

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"❌ Foydalanuvchi ({target_cid}) so‘rovi rad etildi.", parse_mode="HTML")

        try:
            await bot.send_message(
                chat_id=int(target_cid),
                text="❌ <b>Kechirasiz, sizning so‘rovingiz administrator tomonidan rad etildi.</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass
        await callback.answer("Rad etildi!")

    # --- STANDARD MENU COMMANDS ---
    @dp.message(F.text == "📌 Mening vazifalarim")
    async def show_my_tasks(message: types.Message):
        is_auth, _, _ = check_user_access(message.from_user.id)
        if not is_auth:
            await message.answer("⛔️ Kirish cheklangan. Administrator tasdig‘i talab etiladi.")
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT item_code, task_description, deadline_text, status FROM work_plan_items ORDER BY id ASC LIMIT 5")
        tasks = cursor.fetchall()
        conn.close()

        if not tasks:
            await message.answer("Sizga biriktirilgan faol vazifalar topilmadi.")
            return

        res = "📋 <b>Sizning shaxsiy ish rejangizdagi dolzarb vazifalar:</b>\n\n"
        for t in tasks:
            badge = "🟢" if t['status'] == 'Bajarildi' else ("🟡" if t['status'] == 'Kutilmoqda' else "🔴")
            res += f"{badge} <b>{t['item_code']}-band:</b> {t['task_description'][:120]}...\n"
            res += f"   📅 Muddati: {t['deadline_text'] or 'Doimiy'}\n\n"

        await message.answer(res, parse_mode="HTML")

    @dp.message(F.text == "🏢 Kelib tushgan o‘rganishlar")
    async def show_district_assignments(message: types.Message):
        is_auth, _, _ = check_user_access(message.from_user.id)
        if not is_auth:
            await message.answer("⛔️ Kirish cheklangan. Administrator tasdig‘i talab etiladi.")
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT a.assignment_title, a.deadline_date, a.status, d.name as district_name
        FROM task_district_assignments a
        JOIN districts d ON a.district_id = d.id
        ORDER BY a.id DESC LIMIT 6
        """)
        assignments = cursor.fetchall()
        conn.close()

        if not assignments:
            await message.answer("Hududlarga yuklatilgan o‘rganish vazifalari mavjud emas.")
            return

        res = "🏢 <b>Boshqarma ish rejasidan kelib tushgan o‘rganish vazifalari:</b>\n\n"
        for a in assignments:
            res += f"📍 <b>{a['district_name']}</b>: {a['assignment_title']}\n"
            res += f"   📅 Ijro muddati: {a['deadline_date'] or 'Belgilanmagan'}\n"
            res += f"   📌 Holati: <b>{a['status']}</b>\n\n"

        await message.answer(res, parse_mode="HTML")

    @dp.message(F.text == "📊 15-talik monitoring")
    async def show_15_talik_summary(message: types.Message):
        is_auth, _, _ = check_user_access(message.from_user.id)
        if not is_auth:
            await message.answer("⛔️ Kirish cheklangan. Administrator tasdig‘i talab etiladi.")
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT district_id) as submitted_count FROM monthly_15_submissions WHERE year = 2026 AND month = 8 AND submission_status = 'Topshirildi'")
        row = cursor.fetchone()
        submitted = row['submitted_count'] if row else 0
        conn.close()

        text = (
            "📊 <b>Oylik '15-talik' monitoring holati (2026-yil Avgust):</b>\n\n"
            f"✅ Hisobot topshirgan tumanlar: <b>{submitted} / 19 ta</b> (100%)\n"
            "⏳ Keyingi hisobot topshirish muddati: <b>15-oktabr 18:00</b>\n\n"
            "<i>Eslatma: Har oyning 15-sanasi soat 18:00 dan so‘ng tizim avtomatik bloklanadi!</i>"
        )
        await message.answer(text, parse_mode="HTML")

    @dp.message(F.text == "🚨 10-kunlik nazorat (Hodisalar)")
    async def show_incidents_summary(message: types.Message):
        is_auth, _, _ = check_user_access(message.from_user.id)
        if not is_auth:
            await message.answer("⛔️ Kirish cheklangan. Administrator tasdig‘i talab etiladi.")
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM juvenile_incidents WHERE status = 'Nazoratda'")
        active_cnt = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM juvenile_incidents WHERE days_remaining <= 3 AND status = 'Nazoratda'")
        critical_cnt = cursor.fetchone()['cnt']
        conn.close()

        text = (
            "🚨 <b>Voyaga yetmaganlar bilan bog‘liq favqulodda hodisalar nazorati:</b>\n\n"
            f"• Jami 10 kunlik nazoratdagi holatlar: <b>{active_cnt} ta</b>\n"
            f"• ⚠️ Muddat tugashiga 3 kun va undan kam qolganlar: <b>{critical_cnt} ta</b>\n\n"
            "Maktab va tuman mas’ullari ushbu holatlar bo‘yicha zudlik bilan ustoz-murabbiy biriktirib, to‘garakka jalb qilish dalolatnomasini tizimga yuklashi shart."
        )
        await message.answer(text, parse_mode="HTML")

    @dp.message(F.text == "📤 Hisobot topshirish")
    async def prompt_report_submission(message: types.Message, state: FSMContext):
        is_auth, _, _ = check_user_access(message.from_user.id)
        if not is_auth:
            await message.answer("⛔️ Kirish cheklangan. Administrator tasdig‘i talab etiladi.")
            return
        await state.set_state(ReportSubmissionState.waiting_for_report)
        text = (
            "📤 <b>Ijro hisoboti topshirish:</b>\n\n"
            "Iltimos, topshirmoqchi bo‘lgan hisobotingiz matnini yozing yoki tasdiqlovchi <b>Word (.docx), PDF yoki rasm (.jpg)</b> faylini yuboring."
        )
        await message.answer(text, parse_mode="HTML")

    @dp.message(ReportSubmissionState.waiting_for_report)
    async def process_report_submission(message: types.Message, state: FSMContext):
        from app.services.storage_service import get_assignment_storage_path, sanitize_filename, BASE_STORAGE_DIR
        user_fio = message.from_user.full_name
        proof_text = message.text or message.caption or "Telegram bot orqali yuborilgan hisobot"
        now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_chat_id = ?", (str(message.from_user.id),))
        u_row = cursor.fetchone()

        assignment_id = 1
        folder_path = os.path.join(BASE_STORAGE_DIR, "Telegram_Kelgan_Hujjatlar")
        district_name = "Noma'lum"

        if u_row and u_row['district_id']:
            cursor.execute("""
            SELECT id FROM task_district_assignments 
            WHERE district_id = ? AND status != 'Tasdiqlandi'
            ORDER BY id DESC LIMIT 1
            """, (u_row['district_id'],))
            ass_row = cursor.fetchone()
            if ass_row:
                assignment_id = ass_row['id']
                meta = get_assignment_storage_path(assignment_id)
                folder_path = meta['folder_path']
                district_name = meta['district_name']

        os.makedirs(folder_path, exist_ok=True)
        saved_filename = ""
        saved_path = ""

        if message.document:
            file_id = message.document.file_id
            clean_doc_name = sanitize_filename(message.document.file_name)
            saved_filename = f"{now_str}_{clean_doc_name}"
            dest = os.path.join(folder_path, saved_filename)
            file = await bot.get_file(file_id)
            await bot.download_file(file.file_path, dest)
            saved_path = dest
        elif message.photo:
            photo = message.photo[-1]
            saved_filename = f"{now_str}_tg_photo.jpg"
            dest = os.path.join(folder_path, saved_filename)
            file = await bot.get_file(photo.file_id)
            await bot.download_file(file.file_path, dest)
            saved_path = dest

        # Avtomatik pasport yozish
        passport_file = os.path.join(folder_path, f"Hisobot_Pasporti_{now_str}.txt")
        with open(passport_file, "w", encoding="utf-8") as pf:
            pf.write(f"Topshiruvchi: {user_fio} (Chat ID: {message.from_user.id})\nHudud: {district_name}\nVaqt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\nIzoh: {proof_text}\nFayl: {saved_filename}\nPapka: {folder_path}\n")

        # Save to DB
        cursor.execute("""
        INSERT INTO execution_proofs (
            target_type, target_id, submitted_by_fio, proof_text, attachment_paths, approval_status
        ) VALUES ('task_district_assignment', ?, ?, ?, ?, 'Kutilmoqda')
        """, (assignment_id, user_fio, proof_text, json.dumps([saved_path] if saved_path else [])))
        proof_id = cursor.lastrowid

        cursor.execute("UPDATE task_district_assignments SET status = 'Hisobot topshirildi' WHERE id = ?", (assignment_id,))
        conn.commit()
        conn.close()

        await state.clear()
        reply_text = (
            "✅ <b>Hisobotingiz muvaffaqiyatli qabul qilindi!</b>\n\n"
            f"🔢 Hisobot ID: <b>#{proof_id}</b>\n"
            f"👤 Mas’ul: {user_fio}\n"
            f"📝 Mazmuni: {proof_text[:120]}\n\n"
            "<i>Hujjat Boshqarma administratoriga yuborildi. Tasdiqlanganidan so‘ng xabar olasiz.</i>"
        )
        await message.answer(reply_text, parse_mode="HTML", reply_markup=get_main_keyboard())

        # Notify Admins with 1-Click Inline Approval Buttons!
        admin_cids = get_admin_chat_ids()
        admin_markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"approve_proof_{proof_id}"),
                InlineKeyboardButton(text="🔄 Qaytarish", callback_data=f"reject_proof_{proof_id}")
            ]
        ])
        admin_alert = (
            "📥 <b>YANGI HISOBOT KELIB TUSHDI!</b>\n"
            f"🔢 Raqami: #{proof_id}\n"
            f"👤 Yuboruvchi: <b>{user_fio}</b> (Chat ID: {message.from_user.id})\n"
            f"📝 Izoh: {proof_text[:150]}\n"
            f"📎 Fayl: {'Mavjud' if saved_path else 'Mavjud emas'}\n\n"
            "<i>Ushbu hisobotni quyidagi tugmalar orqali 1-klikda tasdiqlashingiz yoki qaytarishingiz mumkin:</i>"
        )
        for acid in admin_cids:
            try:
                await bot.send_message(chat_id=acid, text=admin_alert, parse_mode="HTML", reply_markup=admin_markup)
            except Exception:
                pass

    @dp.message(F.text == "👤 Profil va Sozlamalar")
    async def show_profile(message: types.Message):
        is_admin = str(message.from_user.id) in get_admin_chat_ids()
        text = (
            "👤 <b>Foydalanuvchi ma’lumotlari:</b>\n\n"
            f"• F.I.Sh: <b>{message.from_user.full_name}</b>\n"
            f"• Telegram ID: <code>{message.from_user.id}</code>\n"
            f"• Username: @{message.from_user.username or 'ko‘rsatilmagan'}\n"
            f"• Tizim roli: <b>{'Bosh administrator' if is_admin else 'Tuman koordinatori'}</b>\n"
            "• Holat: 🟢 Faol\n\n"
            "<i>Admin buyruqlari: /admin, /broadcast, /digest</i>"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard(is_admin))

    print("[Telegram Bot] Bot polling successfully started with Admin broadcast & 1-click approvals.")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(start_bot())
