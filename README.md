# Farg‘ona viloyati Maktabgacha va maktab ta’limi boshqarmasi
## Ijro Nazorati va Oylik Monitoring Axborot Tizimi (Web-Platforma + Telegram Bot)

Ushbu axborot tizimi Farg‘ona viloyati Maktabgacha va maktab ta’limi boshqarmasi, 19 ta tuman/shahar MMTB bo‘limlari hamda 963 ta umumta’lim maktablari o‘rtasida ijro intizomi, shaxsiy ish rejalari, oylik «15-talik» monitoring va voyaga yetmaganlar profilaktikasi bo‘yicha tezkor nazoratni ta’minlash uchun yaratilgan.

---

## 🏛 Tizim Imkoniyatlari

1. **Shaxsiy va Tashkiliy Ish Rejalari (`/work-plans`):**
   - Boshqarma xodimlarining 5 ta yo‘nalishdagi ish rejalari monitoringi.
   - **Hudud va maktablarga avtomatik/qo‘lda vazifa yuklash:** Rejada tuman yoki maktab o‘rganilishi ko‘rsatilsa, tizim ushbu hududga avtomatik topshiriq sifatida biriktiradi.
2. **Hududiy Vazifalar Monitoringi (`/district-assignments`):**
   - Tuman MMTB va maktablar o‘zlariga tushgan vazifalarni ko‘radi, tayyorgarlik ko‘radi va tasdiqlovchi fayl/hujjat yuklaydi.
3. **Oylik «15-talik» Monitoring (`/monthly-15`):**
   - 19 ta tuman/shahar bo‘yicha 15 ta asosiy yo‘nalish (Notinch oilalar, Ichki nazorat, Profilaktika, Jinoyatchilik, Chet elga ketganlar, Surunkali dars qoldiruvchilar, Targ‘ibot tadbirlari).
   - Har oyning 15-sanasiga qadar avtomatik qabul va muddat o‘tgach bloklash (Lock).
   - Bir tugma bilan 18 sahifali Vazirlik Excel kitobini eksport qilish.
4. **10-kunlik Qat’iy Muddat Nazorati (`/incidents`):**
   - Voyaga yetmaganlar tomonidan sodir etilgan jinoyat va favqulodda hodisalar jurnali.
   - Har bir holat yuzasidan 10 kunlik orqaga hisoblash (Countdown). Maktab mas’uli, MFY va profilaktika inspektori biriktirilishi shart.
5. **Rasmiy Tahliliy Hujjatlar Generatori (`/reports`):**
   - Boshqarma Hay’ati va viloyat hokimligi uchun rasmiy tahliliy Word (`.docx`) ma’lumotnomasini avtomatik shakllantirish (2025 vs 2026 taqqoslama dinamikasi bilan).
   - Vazirlik uchun «15-talik» Excel kitobini generatsiya qilish.
6. **Telegram Bot Integratsiyasi (`app/bot/`):**
   - Shaxsiy vazifalar, hududiy topshiriqlar, hisobot qabul qilish va 5/3/1 kunlik eslatmalar.

---

## 🚀 O‘rnatish va Ishga Tushirish

### 1. Talablar:
- Python 3.10 yoki undan yuqori (tizimda Python 3.14 mavjud)
- Paketlar: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `openpyxl`, `python-docx`, `aiogram`, `requests`

### 2. O‘rnatish:
```bash
cd monitoring_platform
pip install -r requirements.txt
```

### 3. Serverni ishga tushirish:
```bash
python run.py
```
Tizim avtomatik ravishda ma’lumotlar bazasini tekshiradi va serverni `http://127.0.0.1:8080` manzilida ishga tushiradi.

---

## 🤖 Telegram Botni Sozlash

1. Telegramda `@BotFather` orqali yangi bot oching va **API Token** oling.
2. `monitoring_platform` papkasida `.env` faylini yarating yoki tizim muhitiga kiriting:
   ```env
   TELEGRAM_BOT_TOKEN="sizning_bot_tokeningiz"
   PORT=8080
   ```
3. `python run.py` ishga tushirilganda Telegram Bot avtomatik parallel ishga tushadi.

---

## 📁 Loyiha Strukturasi

```
monitoring_platform/
├── app/
│   ├── bot/
│   │   └── telegram_bot.py      # Aiogram 3 Telegram Bot
│   ├── parsers/
│   │   ├── parse_work_plans.py  # Word ish rejalarini import qilish
│   │   ├── parse_15_talik.py    # 15-talik Excel monitoringini import qilish
│   │   └── parse_incidents.py   # Huquqbuzarliklar Excel kitobini import qilish
│   ├── services/
│   │   ├── notification_service.py # Avtomatik 5/3/1 va 10 kunlik muddat nazorati
│   │   └── report_generator.py     # Word va Excel hisobotlarini yaratuvchi
│   ├── db.py                    # SQLite bazasi, modellar va 19 ta tuman
│   └── seed_assignments.py      # Boshlang‘ich hududiy vazifalar
├── data/
│   └── monitoring.db            # Asosiy SQLite ma’lumotlar bazasi
├── static/
│   └── uploads/
│       └── exports/             # Generatsiya qilingan Word va Excel fayllar
├── templates/
│   ├── base.html                # Asosiy shablon (Tailwind, FontAwesome, Chart.js)
│   ├── index.html               # Boshqaruv paneli (KPI, Diagramma, 19 ta tuman)
│   ├── work_plans.html          # Ish rejalari va hududga biriktirish
│   ├── district_assignments.html # Hududlarga yuklatilgan topshiriqlar
│   ├── monthly_15.html          # 15-talik oylik monitoring jadvali
│   ├── incidents.html           # Voyaga yetmaganlar 10 kunlik muddat jurnali
│   └── reports.html             # Hisobotlar va hujjatlar markazi
├── main.py                      # FastAPI Web ilovasi
├── run.py                       # Bir tugma bilan server + bot ishga tushiruvchi
├── requirements.txt
└── README.md
```

---

## 🔒 Xavfsizlik va Zaxiralash (Backup)

Barcha ma’lumotlar `data/monitoring.db` SQLite faylida to‘liq saqlanadi. Zaxiralash uchun har kuni ushbu fayl va `static/uploads/` jildini arxivlab olish kifoya.
