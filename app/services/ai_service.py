# -*- coding: utf-8 -*-
import os
import json
import requests

def _load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6KXrntJgkXrxOZwGhDx4MmzCSEuC1VbVEqnNpMpIN8YLQ")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

def call_gemini(prompt: str, temperature: float = 0.3) -> str:
    """Invokes Google Gemini API with robust error handling."""
    if not GEMINI_API_KEY:
        return "Xatolik: Gemini API kaliti kiritilmagan."

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 2048
        }
    }

    try:
        response = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
            return "Bo'sh javob qaytdi."
        else:
            return f"Gemini API xatoligi ({response.status_code}): {response.text[:200]}"
    except Exception as e:
        return f"Server bilan bog'lanishda xatolik: {str(e)}"

def analyze_incident_ai(student_fio: str, district_name: str, school_name: str, 
                        article: str, details: str, birth_date: str = "") -> dict:
    """
    Analyzes juvenile crime fabula with Gemini AI.
    Returns structured analysis: root cause, risk level, recommendations, and official draft letter.
    """
    prompt = f"""
Siz Farg'ona viloyati Maktabgacha va maktab ta'limi boshqarmasining voyaga yetmaganlar masalalari bo'yicha yuqori malakali eksperti va huquqshunosisiz.
Quyida IIB tomonidan qayd etilgan voyaga yetmagan o'quvchi tomonidan sodir etilgan huquqbuzarlik (jinoyat) ma'lumotlari keltirilgan.

O'QUVCHI MA'LUMOTLARI:
- F.I.Sh: {student_fio}
- Tug'ilgan sana: {birth_date or 'Ko‘rsatilmagan'}
- Hudud: {district_name}
- Maktab / Sinf: {school_name}
- Jinoyat kodeksi moddasi: {article}
- Voqea tafsilotlari (Fabula):
{details}

VAZIFA:
Mazkur holatni chuqur tahlil qiling va O'ZBEK TILIDA quyidagi 4 ta bo'limdan iborat professional xulosa bering:

1. ASL SABAB VA OMILLAR (Nima sababdan ushbu jinoyat sodir bo'ldi? Tungi nazoratsizlik, oilaviy muhit, dars qoldirish, axborot texnologiyalari yoki boshqa? 2-3 ta jumla).
2. XAVF DARAJASI (Faqat bittasini tanlang: Yuqori, O‘rta, Past).
3. AMALIY PROFILAKTIK TAVSIYALAR (Ushbu o'quvchi bilan qayta jinoyat sodir etilishining oldini olish uchun maktab psixologi, MFY va nozir nima qilishi kerak? Aniq 3 ta punkt).
4. RASMIY TALABNOMA XATI LOYIHASI (Farg'ona viloyati MMTB rahbariyati nomidan {district_name} Maktabgacha va maktab ta'limi bo'limi mudiriga hamda {school_name} direktoriga yo'llangan 10 kunlik qat'iy talabnoma xati loyihasi. Unda mas'ullarga nisbatan chora ko'rish, o'quvchini qat'iy nazoratga olish va 10 kun ichida hujjatlar to'plamini topshirish qat'iy talab qilinsin).

JAVOB FORMATI (Faqat toza JSON formatida qaytaring, boshqa ortiqcha so'z yozmang):
{{
  "sabab": "...",
  "xavf_darajasi": "Yuqori / O‘rta / Past",
  "tavsiyalar": [
    "1-tavsiya...",
    "2-tavsiya...",
    "3-tavsiya..."
  ],
  "talabnoma_xati": "Farg'ona viloyati MMTB Talabnomasi matni..."
}}
"""
    raw_response = call_gemini(prompt, temperature=0.2)
    
    # Try parsing JSON
    try:
        cleaned = raw_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        parsed = json.loads(cleaned.strip())
        return {
            "status": "success",
            "sabab": parsed.get("sabab", "Sabab tahlil qilindi."),
            "xavf_darajasi": parsed.get("xavf_darajasi", "O‘rta"),
            "tavsiyalar": parsed.get("tavsiyalar", []),
            "talabnoma_xati": parsed.get("talabnoma_xati", ""),
            "raw_text": raw_response
        }
    except Exception:
        return {
            "status": "partial",
            "sabab": "Tafsilotlar tahlili o'tkazildi.",
            "xavf_darajasi": "O‘rta",
            "tavsiyalar": ["Profilaktika inspektori bilan hamkorlikda o'rganish.", "Ota-onasi bilan suhbat o'tkazish."],
            "talabnoma_xati": raw_response,
            "raw_text": raw_response
        }

def evaluate_actions_ai(student_fio: str, district_name: str, school_name: str,
                        details: str, current_study_status: str,
                        school_resp: str, mfy_resp: str, inspector: str) -> dict:
    """Evaluates 10-day preventive actions reported by the district."""
    prompt = f"""
Siz Farg'ona viloyati MMTB monitoring inspektorisiz.
Quyida voyaga yetmagan o'quvchi tomonidan sodir etilgan jinoyat va u bo'yicha tuman/maktab tomonidan ko'rilgan choralar hisoboti keltirilgan.

HODISA:
- O'quvchi: {student_fio} ({district_name}, {school_name})
- Voqea: {details}

KO'RILGAN CHORALAR VA HISOBOT:
- Maktabdan mas'ul: {school_resp}
- MFYdan mas'ul: {mfy_resp}
- Profilaktika noziri: {inspector}
- O'quvchining hozirgi holati va bandligi: {current_study_status}

VAZIFA:
Mazkur hisobotni baholang:
1. Baho: (Faqat bittasini tanlang: "To‘liq bajarilgan" / "Yetarli emas" / "Formal qog‘ozbozlik")
2. Qisqa xulosa va kamchiliklar (1-2 jumla).

JSON formatida qaytaring:
{{
  "baho": "To‘liq bajarilgan / Yetarli emas / Formal qog‘ozbozlik",
  "izoh": "..."
}}
"""
    raw_response = call_gemini(prompt, temperature=0.2)
    try:
        cleaned = raw_response.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)
        return parsed
    except Exception:
        return {
            "baho": "Yetarli emas",
            "izoh": raw_response[:200]
        }

def evaluate_district_report_ai(assignment_title: str, district_name: str, report_text: str, file_name: str = "") -> dict:
    """Evaluates whether an uploaded district task execution report is genuine or formalistic."""
    prompt = f"""
Siz Farg'ona viloyati Maktabgacha va maktab ta'limi boshqarmasining Ijro intizomi va nazorati bosh mutaxassisisiz.
Quyida tuman tomonidan topshiriq ijrosi yuzasidan topshirilgan hisobot keltirilgan.

TOPSHIRIQ: {assignment_title}
HUDUD: {district_name}
YUKLANGAN FAYL: {file_name or 'Fayl biriktirilmagan'}
HISOBOT MATNI:
{report_text}

VAZIFA:
Ushbu hisobotni xolis baholang:
1. Baho: (To‘liq bajarilgan / Qisman bajarilgan / Formal qog‘ozbozlik)
2. Sifat darajasi: (A’lo / Qoniqarli / Qoniqarsiz)
3. Ekspert xulosasi (Kamchiliklari yoki ijobiy jihati haqida 2-3 jumla).
4. Tavsiya (Rahbariyatga qabul qilish yoki qaytarish bo'yicha).

JSON formatida qaytaring:
{{
  "baho": "To‘liq bajarilgan / Qisman bajarilgan / Formal qog‘ozbozlik",
  "sifat": "A’lo / Qoniqarli / Qoniqarsiz",
  "xulosa": "...",
  "tavsiya": "Qabul qilish / Qayta ishlashga qaytarish"
}}
"""
    raw = call_gemini(prompt, temperature=0.2)
    try:
        cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)
    except Exception:
        return {
            "baho": "Qoniqarli",
            "sifat": "Qoniqarli",
            "xulosa": raw[:250],
            "tavsiya": "Ko'rib chiqilmoqda"
        }

def generate_executive_briefing_ai(kpi_data: list, crime_stats: dict, plan_stats: dict, period_name: str = "Haftalik") -> dict:
    """
    Generates a high-level executive analytical report for Boshqarma Boshlig'i and Apparat yig'ilishi.
    Includes top performing, critical lagging districts, crime hotspots, and actionable management resolutions.
    """
    # Prepare district summary for prompt
    top_districts = [f"{d['name']} ({d['score']} ball, {d['zone']})" for d in kpi_data[:4]]
    bottom_districts = [f"{d['name']} ({d['score']} ball, {d['zone']})" for d in kpi_data[-4:]]

    prompt = f"""
Siz Farg'ona viloyati Maktabgacha va maktab ta'limi boshqarmasi rahbariyatining Bosh maslahatchisi va tahlilchisisiz.
Quyida Farg'ona viloyatidagi barcha 19 ta tuman va shahar bo'yicha real ma'lumotlar keltirilgan:

DAVR: {period_name} ijro intizomi va profilaktika holati.

IJRO INTIZOMI VA REYTING KO'RSATKICHLARI:
- Namunali (Top) tumanlar: {', '.join(top_districts)}
- Tanqidiy (Quyi) tumanlar: {', '.join(bottom_districts)}
- Rejadagi topshiriqlar: Jami {plan_stats.get('total', 0)} ta, bajarilgan {plan_stats.get('completed', 0)} ta, kechikayotgan {plan_stats.get('overdue', 0)} ta.

VOYAGA YETMAGANLAR JINOYATCHILIGI:
- Jami qayd etilgan jinoyatlar: {crime_stats.get('total', 0)} ta
- Shoshilinch nazoratdagi (10 kunlik muddat tugayotgan): {crime_stats.get('urgent', 0)} ta
- Ko'p jinoyat qayd etilgan tumanlar: {crime_stats.get('hotspots', 'Mavjud emas')}

VAZIFA:
Boshqarma boshlig'i va apparat yig'ilishi uchun O'ZBEK TILIDA rasmiy, tanqidiy va chuqur TAHLILIY AXBOROTNOMA (Nutq va Qaror loyihasi) tayyorlang:

1. UMUMIY VAZIYAT VA BAHOLASH (2-3 jumla).
2. NAMUNALI HUDUDLAR (Nega ular yutuqqa erishdi? 2 ta punkt).
3. TANQIDIY HUDUDLAR VA MAS'ULIYATSIZLIK (Qaysi tumanlar ishi qoniqarsiz va qaysi yo'nalishda orqada? 3 ta punkt).
4. VOYAGA YETMAGANLAR PROFILAKTIKASI BO'YICHA XULOSA (Maktab va IIB hamkorligi qayerda oqsayapti?).
5. BOSHQARMA BOSHLIG'INING QAT'IY TOPSHIRIQLARI (Apparat yig'ilishi bayonnomasiga kiritiladigan 5 ta aniq topshiriq — kimga, qanday muddat, qanday chora).

JSON formatida qaytaring:
{{
  "sarlavha": "Farg'ona viloyati MMTB Apparat yig'ilishi Tahliliy Axborotnomasi",
  "umumiy_vaziyat": "...",
  "yutuqlar": ["...", "..."],
  "tanqidiy_tahlil": ["...", "...", "..."],
  "jinoyatchilik_tahlili": "...",
  "topshiriqlar": [
    "1-topshiriq...",
    "2-topshiriq...",
    "3-topshiriq...",
    "4-topshiriq...",
    "5-topshiriq..."
  ],
  "yakuniy_xulosa": "..."
}}
"""
    raw = call_gemini(prompt, temperature=0.25)
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        parsed = json.loads(cleaned.strip())
        parsed["status"] = "success"
        return parsed
    except Exception:
        return {
            "status": "partial",
            "sarlavha": "Tahliliy Axborotnoma",
            "umumiy_vaziyat": raw[:300],
            "yutuqlar": ["Namunali tumanlar ko'rsatkichlari ijobiy."],
            "tanqidiy_tahlil": ["Kechikkan topshiriqlar bo'yicha mas'uliyatni oshirish zarur."],
            "jinoyatchilik_tahlili": "10 kunlik nazorat muddatlarini qat'iy nazoratga olish zarur.",
            "topshiriqlar": ["Tuman bo'lim mudirlariga ogohlantirish berish.", "Profilaktik tadbirlarni kuchaytirish."],
            "yakuniy_xulosa": raw[:200]
        }
