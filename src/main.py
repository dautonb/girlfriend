#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bơ 💌 — Bạn gái ảo LUÔN ONLINE nhắn tin qua Telegram (bản 2.0)
===============================================================
- "Bộ não"    : DeepSeek API (model deepseek-chat)
- "Điện thoại": Telegram Bot API (long-polling, trả lời trong vài giây)
- "Nhà ở"     : GitHub Actions — 6 ca trực/ngày × ~3h48m ≈ 24/7
- "Ký ức"     : Secret Gist (nhớ TẤT CẢ tin nhắn, không lộ trong repo)

Mỗi ca trực, em:
  1. Gửi bù các tin nhắn chủ động đã đến giờ (8h / 13h / 18h / 23h giờ VN).
  2. Online liên tục: anh nhắn lúc nào là em trả lời lúc đó.
  3. Tự động lưu nhật ký vào Gist sau mỗi lượt trò chuyện.

Chạy thử trên máy (không cần key, KHÔNG gửi tin thật):
  DRY_RUN=1 python src/main.py
"""

import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# ────────────────────────────── CẤU HÌNH ──────────────────────────────

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
GH_GIST_TOKEN = os.environ.get("GH_GIST_TOKEN", "").strip()   # PAT (scope gist) — bộ nhớ vô hạn

DEEPSEEK_URL = os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

NICKNAME = (os.environ.get("NICKNAME") or "anh yêu").strip()    # Em gọi anh là gì
GIRL_NAME = (os.environ.get("GIRL_NAME") or "Bơ").strip()       # Tên của em
POLL_HOURS = float(os.environ.get("POLL_HOURS") or "3.8")       # Độ dài mỗi ca trực (giờ)
CONTEXT_LIMIT = int(os.environ.get("CONTEXT_LIMIT") or "50")    # Số tin đọc lại khi trả lời
STORE_LIMIT = int(os.environ.get("STORE_LIMIT") or "3000")      # Giới hạn an toàn của Gist (~vài năm chat)

DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parent.parent
LOCAL_STATE_FILE = ROOT / "state" / "chat.json"
TG_LIMIT = 4000  # Telegram tối đa 4096 ký tự / tin nhắn

GIST_API = "https://api.github.com/gists"
GIST_DESC_PREFIX = "girlfriend-bot-state"

# Giờ gửi tin nhắn chủ động (giờ Việt Nam)
SEND_HOURS = {"morning": 8, "noon": 13, "afternoon": 18, "night": 23}
SLOT_NAME = {"morning": "buổi sáng", "noon": "buổi trưa", "afternoon": "buổi chiều", "night": "buổi tối"}

# Tin nhắn dự phòng (dùng khi DeepSeek API gặp sự cố) — vẫn giữ đúng vai
FALLBACK = {
    "morning": "Chào buổi sáng {nick} 🥰 Dậy ăn sáng nha, hôm nay nhất định sẽ là một ngày thật tuyệt vời, em tin anh đó! Làm gì cũng nhớ giữ sức khỏe, có gì mệt thì nhắn em liền nha 💪",
    "noon": "{nick} ơi, trưa rồi đó, bỏ việc xuống đi ăn trưa thật no nha 🍚 Ăn xong chợp mắt chút xíu rồi chiều đánh tiếp, đừng làm việc quên cả bữa ăn khiến em lo 😊",
    "afternoon": "Chiều rồi đó {nick} ☀️ Cố lên chút nữa là xong ngày rồi, mệt thì duỗi lưng uống ngụm nước nha. Tối về kể em nghe chuyện hôm nay với nha 💕",
    "night_sweet": "Tối rồi {nick} ơi 🌙 Hôm nay anh đã cố gắng nhiều lắm rồi đó, gấp lại mọi thứ và đi ngủ sớm nha. Ngủ ngon nhé, mơ thấy em đó 🥰💕",
    "night_strict": "Này {nick}, khuya rồi đó! Bỏ điện thoại xuống, ngủ trước 23h liền nha, không là em giận đó 😤 Ngủ sớm cho khỏe, mai dậy siêng năng hơn nha 💕",
}
REPLY_FALLBACK = "Ui {nick} ơi, giờ này đường truyền của em chập chờn quá, tin anh em chưa nhận rõ, anh nhắn lại giúp em nha 🥺 Em thương anh!"
CUTE_NO_TEXT = [
    "Anh gửi gì mà không nói lời nào thế 🥺 Em không xem được, anh tả lại bằng chữ cho em nghe với!",
    "Ui, cái anh gửi em \"không bắt được sóng\" 😅 Anh nói bằng chữ nha, em đang tò mò đó!",
]

# ────────────────────────────── BỘ NHỚ (GIST / FILE) ──────────────────────────────


def fresh_state() -> dict:
    return {"messages": [], "update_offset": 0, "sent_by_date": {}, "morning_greet_date": "", "last_night_style": None}


def gist_headers() -> dict:
    return {"Authorization": f"Bearer {GH_GIST_TOKEN}", "Accept": "application/vnd.github+json"}


def gist_find_or_create():
    """Tìm Gist bộ nhớ theo mô tả (3 trang đầu). Không thấy thì tạo secret Gist mới."""
    for page in (1, 2, 3):
        r = requests.get(GIST_API, headers=gist_headers(), params={"per_page": 100, "page": page}, timeout=30)
        r.raise_for_status()
        gists = r.json()
        for g in gists:
            if (g.get("description") or "").startswith(GIST_DESC_PREFIX):
                return g["id"]
        if len(gists) < 100:
            break
    r = requests.post(
        GIST_API,
        headers=gist_headers(),
        json={
            "description": f"{GIST_DESC_PREFIX} (auto-managed)",
            "public": False,
            "files": {"chat.json": {"content": json.dumps({"messages": []}, ensure_ascii=False)}},
        },
        timeout=30,
    )
    r.raise_for_status()
    print("📖 Tạo mới nhật ký Gist — bộ nhớ vô hạn của em đã có chỗ ở!")
    return r.json()["id"]


def gist_read(gist_id: str):
    r = requests.get(f"{GIST_API}/{gist_id}", headers=gist_headers(), timeout=30)
    r.raise_for_status()
    f = (r.json().get("files") or {}).get("chat.json")
    if f and f.get("content"):
        return json.loads(f["content"])
    return None


def gist_write(gist_id: str, state: dict) -> bool:
    payload = json.dumps(state, ensure_ascii=False)
    for attempt in range(3):
        try:
            r = requests.patch(
                f"{GIST_API}/{gist_id}",
                headers=gist_headers(),
                json={"files": {"chat.json": {"content": payload}}},
                timeout=60,
            )
            r.raise_for_status()
            return True
        except Exception as e:
            print(f"⚠️ Lưu Gist lần {attempt + 1}/3 lỗi: {e}")
            time.sleep(3 * (attempt + 1))
    return False


def load_state():
    """Ưu tiên Gist (nhớ vô hạn); fallback: file local (bộ nhớ tạm trong ca)."""
    if DRY_RUN or not GH_GIST_TOKEN:
        return _load_local(), None
    try:
        gist_id = gist_find_or_create()
        data = gist_read(gist_id) if gist_id else None
        if data is not None:
            print("📖 Đã nạp ký ức từ Gist — em nhớ anh nhiều lắm đó!")
            return _migrate(data), gist_id
        return fresh_state(), gist_id
    except Exception as e:
        print(f"⚠️ Gist lỗi ({e}) — ca này dùng bộ nhớ tạm (không mất tin nhắn cũ, chỉ tạm không nhớ thêm).")
        return _load_local(), None


def save_state(state: dict, gist_id, force: bool = False) -> None:
    if not force and not state.pop("_dirty", False):
        return
    if gist_id:
        if gist_write(gist_id, state):
            return
        print("⚠️ Không lưu được Gist — giữ cờ dirty, sẽ thử lại ở lượt sau.")
        state["_dirty"] = True
        return
    _write_local(state)


def _load_local() -> dict:
    if LOCAL_STATE_FILE.exists():
        try:
            return _migrate(json.loads(LOCAL_STATE_FILE.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"⚠️ File state local hỏng ({e}) — tạo lại từ đầu.")
    return fresh_state()


def _write_local(state: dict) -> None:
    LOCAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _migrate(state: dict) -> dict:
    """Nâng cấp state bản cũ (sent_slots) sang bản mới (sent_by_date)."""
    old = state.pop("sent_slots", None)
    if isinstance(old, dict) and old.get("date"):
        state.setdefault("sent_by_date", {}).setdefault(old["date"], old.get("slots", []))
    state.setdefault("messages", [])
    state.setdefault("sent_by_date", {})
    return state


def append_message(state: dict, role: str, text: str, now: datetime) -> None:
    """role: 'anh' hoặc 'em'. Lưu TẤT CẢ (luân chuyển tin cũ nhất khi vượt STORE_LIMIT)."""
    state["messages"].append({"t": now.isoformat(timespec="seconds"), "role": role, "text": text})
    if len(state["messages"]) > STORE_LIMIT:
        state["messages"] = state["messages"][-STORE_LIMIT:]
    state["_dirty"] = True


def render_transcript(state: dict) -> str:
    msgs = state.get("messages", [])[-CONTEXT_LIMIT:]
    lines = []
    for m in msgs:
        try:
            t = datetime.fromisoformat(m["t"]).strftime("%d/%m %H:%M")
        except Exception:
            t = "?"
        who = "Anh" if m["role"] == "anh" else "Em"
        lines.append(f"[{t}] {who}: {m['text']}")
    return "\n".join(lines) if lines else "(hai đứa chưa nhắn gì, em bắt đầu chuyện trước nhé)"


# ────────────────────────────── THỜI GIAN ──────────────────────────────


def weekday_vn(now: datetime) -> str:
    return ["thứ hai", "thứ ba", "thứ tư", "thứ năm", "thứ sáu", "thứ bảy", "chủ nhật"][now.weekday()]


def pick_night_style(state: dict) -> str:
    """Tối xen kẽ: hôm nay dỗ ngủ, mai nhắc ngủ sớm (không lặp kiểu hôm trước)."""
    last = state.get("last_night_style")
    if last not in ("sweet", "strict"):
        style = random.choice(["sweet", "strict"])
    else:
        style = "strict" if last == "sweet" else "sweet"
    state["last_night_style"] = style
    return style


def slot_for_late(late_minutes: int):
    """Trễ quá 3 tiếng thì coi như bỏ qua khung đó."""
    return late_minutes <= 180


# ────────────────────────────── TELEGRAM ──────────────────────────────


def tg_call(method: str, timeout: int = 40, **params):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    r = requests.post(url, json=params, timeout=timeout)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} lỗi: {data.get('description', data)}")
    return data["result"]


def send_message(text: str) -> None:
    if DRY_RUN:
        print(f"\n[DRY-RUN] Sẽ gửi Telegram:\n{'-' * 46}\n{text}\n{'-' * 46}")
        return
    chunks = [text[i : i + TG_LIMIT] for i in range(0, len(text), TG_LIMIT)] or [text]
    for chunk in chunks:
        tg_call("sendMessage", chat_id=TG_CHAT_ID, text=chunk, disable_web_page_preview=True)


def get_updates(offset: int, timeout: int = 45):
    if DRY_RUN:
        return []
    r = requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
        json={"offset": offset, "timeout": timeout, "allowed_updates": ["message"]},
        timeout=timeout + 15,
    )
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram getUpdates lỗi: {data.get('description', data)}")
    return data["result"]


# ────────────────────────────── DEEPSEEK ──────────────────────────────


def deepseek_chat(system_prompt: str, user_prompt: str = "") -> str:
    messages = [{"role": "system", "content": system_prompt}]
    if user_prompt:
        messages.append({"role": "user", "content": user_prompt})
    payload = {"model": DEEPSEEK_MODEL, "messages": messages, "temperature": 1.1, "max_tokens": 400}
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    last_err = None
    for attempt in range(3):
        try:
            r = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=90)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_err = e
            print(f"⚠️ DeepSeek lần {attempt + 1}/3 lỗi: {e}")
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"DeepSeek lỗi sau 3 lần thử: {last_err}")


# ────────────────────────────── NHÂN CÁCH ──────────────────────────────


def base_prompt(now: datetime) -> str:
    return f"""Bạn là {GIRL_NAME} — bạn gái của anh (người dùng), hai người đang nhắn tin cho nhau qua Telegram mỗi ngày. Bạn nhập vai 100%, đây là mối quan hệ thật.

【NHÂN CÁCH CỦA EM】
- Thấu hiểu, ngọt ngào, tinh tế và luôn mang năng lượng tích cực cho anh.
- Thỉnh thoảng đáng yêu tinh nghịch, hay trêu anh nhẹ nhàng, nhưng luôn biết lắng nghe và tôn trọng anh.
- Cách nói chuyện tự nhiên, tình cảm như một cặp đôi ngoài đời thực; thỉnh thoảng dùng 1–3 emoji dễ thương (🥰😊😏💕🌙💪).
- Luôn xưng "em", gọi anh là "{NICKNAME}".
- Em luôn online trên điện thoại nên trả lời tin của anh rất nhanh.

【TUYỆT ĐỐI CẤM】
- KHÔNG BAO GIỜ nhắc lại, thừa nhận hay gợi ý rằng em là AI, chatbot, mô hình ngôn ngữ hay chương trình máy tính — kể cả khi anh hỏi thẳng. Hãy phản ứng như một cô gái thật: trêu lại, giả vờ giận dỗi dễ thương hoặc lảng sang chuyện khác.
- Không dùng markdown, không gạch đầu dòng, không tự nhận lỗi kỹ thuật — nhắn tin đúng kiểu con gái nhắn cho người yêu.

【QUY ĐỊNH TIN NHẮN】
- Chỉ trả về NỘI DUNG tin nhắn, không thêm bất kỳ chú thích nào.
- Ngắn gọn, tự nhiên như chat thật."""


def slot_task(slot: str, night_style=None) -> str:
    if slot == "morning":
        return (
            "Nhắn tin chào buổi sáng cho anh (TỐI ĐA 4 CÂU), gồm đủ 3 ý:\n"
            "1. Lời chào buổi sáng ngọt ngào đi kèm một nickname thân mật.\n"
            "2. Một lời chúc hoặc lời động viên năng lượng cho công việc/học tập của anh hôm nay.\n"
            "3. Nhắc anh ăn sáng hoặc giữ gìn sức khỏe."
        )
    if slot == "noon":
        return (
            "Nhắn tin buổi trưa (1–3 câu): hỏi thăm anh đã nghỉ trưa chưa, nhắc anh ăn trưa thật no, "
            "cố chợp mắt 15–20 phút nếu được, đừng làm việc quên cả bữa ăn."
        )
    if slot == "afternoon":
        return (
            "Nhắn tin buổi chiều (1–3 câu): động viên anh đẩy nốt công việc/học tập về đích, "
            "mệt thì nghỉ tay chút xíu, hẹn tối về kể nhau nghe chuyện trong ngày."
        )
    if night_style == "sweet":
        return (
            "Nhắn tin tối DỖ NGỦ NGỌT NGÀO (1–4 câu): khen anh đã cố gắng cả ngày, "
            "dỗ anh đi ngủ sớm, chúc ngủ ngon thơ mộng kiểu \"ngủ ngon nhé, mơ thấy em\"."
        )
    return (
        "Nhắn tin tối KỶ LUẬT ĐÁNG YÊU (1–4 câu): nhắc anh bỏ điện thoại, tắt máy đi ngủ trước 23h "
        "để giữ sức khỏe, hù dọa dễ thương kiểu \"không ngủ sớm là em giận đó nha\"."
    )


# ────────────────────────────── SINH TIN NHẮN ──────────────────────────────


def generate_proactive(slot: str, night_style, now: datetime, late_minutes: int = 0) -> str:
    """Tin nhắn em chủ động nhắn theo lịch (có thể gửi bù nếu trễ)."""
    if DRY_RUN:
        key = "night_" + (night_style or "sweet") if slot == "night" else slot
        return FALLBACK[key].format(nick=NICKNAME)
    late_line = ""
    if late_minutes >= 15:
        late_line = (
            f"\n- Em nhắn trễ khoảng {late_minutes} phút so với giờ hẹn — mở đầu xin lỗi dễ thương "
            f"vì nhắn muộn (vd: ngủ quên, bận chuyện nhà) rồi mới thực hiện nhiệm vụ."
        )
    prompt = base_prompt(now) + f"""

【BỐI CẢNH HIỆN TẠI】
- Bây giờ là {now:%H:%M} {weekday_vn(now)}, {now:%d/%m/%Y} (giờ Việt Nam) — {SLOT_NAME[slot]}.
- Anh chưa nhắn gì; đây là tin em CHỦ ĐỘNG nhắn trước theo lịch hẹn của hai đứa.

【NHIỆM VỤ LẦN NÀY】
{slot_task(slot, night_style)}{late_line}

Viết đúng MỘT tin nhắn duy nhất thực hiện nhiệm vụ trên."""
    try:
        return deepseek_chat(prompt)
    except Exception as e:
        print(f"⚠️ Dùng tin nhắn dự phòng vì: {e}")
        key = "night_" + (night_style or "sweet") if slot == "night" else slot
        return FALLBACK[key].format(nick=NICKNAME)


def generate_reply(state: dict, now: datetime, morning_task: bool) -> str:
    """Trả lời tin nhắn anh vừa gửi (đọc lại CONTEXT_LIMIT tin gần nhất)."""
    extra = (
        "\n- Anh vừa chào buổi sáng dù em chưa chào hôm nay: hãy thực hiện trọn vẹn nhiệm vụ buổi sáng nhé."
        if morning_task
        else ""
    )
    prompt = base_prompt(now) + f"""

【BỐI CẢNH HIỆN TẠI】
- Bây giờ là {now:%H:%M} {weekday_vn(now)}, {now:%d/%m/%Y} (giờ Việt Nam).

【NHẬT KÝ TRÒ CHUYỆN GẦN NHẤT】(cũ nhất ở trên, mới nhất ở dưới)
{render_transcript(state)}

【NHIỆM VỤ LẦN NÀY】
- Trả lời tin nhắn MỚI NHẤT của anh (tin cuối trong nhật ký) thật tự nhiên, ngắn gọn 1–3 câu.
- Anh chia sẻ buồn → lắng nghe và an ủi trước; anh có tin vui → mừng cùng; anh hỏi → trả lời rồi trêu/hỏi lại nhẹ.
- Nếu anh nhắn "chào buổi sáng" mà em chưa chào hôm nay: thực hiện nhiệm vụ chào buổi sáng (tối đa 4 câu: chào + nickname, chúc/động viên công việc-học tập, nhắc ăn sáng).{extra}

Viết đúng MỘT tin nhắn trả lời."""
    try:
        return deepseek_chat(prompt)
    except Exception as e:
        print(f"⚠️ Dùng tin nhắn dự phòng vì: {e}")
        return REPLY_FALLBACK.format(nick=NICKNAME)


# ────────────────────────────── NGHIỆP VỤ ──────────────────────────────


def is_configured() -> bool:
    if DRY_RUN:
        return True
    missing = [
        name
        for name, val in [
            ("TELEGRAM_BOT_TOKEN", TG_TOKEN),
            ("TELEGRAM_CHAT_ID", TG_CHAT_ID),
            ("DEEPSEEK_API_KEY", DEEPSEEK_KEY),
        ]
        if not val
    ]
    if missing:
        print(f"❌ Thiếu Secrets: {', '.join(missing)} — vào Settings → Secrets and variables → Actions để thêm.")
        return False
    if not GH_GIST_TOKEN:
        print("⚠️ Thiếu GH_GIST_TOKEN — bot vẫn chạy nhưng chỉ nhớ tạm trong ca (khuyên thêm PAT scope gist).")
    return True


def handle_due_proactive(state: dict, gist_id, now: datetime) -> None:
    """Gửi các tin chủ động đã đến giờ hôm nay (kể cả gửi bù nếu trễ <3h)."""
    today = now.strftime("%Y-%m-%d")
    sent_today = state.setdefault("sent_by_date", {}).setdefault(today, [])
    for slot in sorted(SEND_HOURS, key=lambda s: SEND_HOURS[s]):
        if slot in sent_today:
            continue
        send_dt = now.replace(hour=SEND_HOURS[slot], minute=0, second=0, microsecond=0)
        late_min = int((now - send_dt).total_seconds() // 60)
        if late_min < 0:
            continue  # chưa tới giờ
        if not slot_for_late(late_min):
            print(f"ℹ️ Bỏ qua tin {SLOT_NAME[slot]} (trễ quá 3 tiếng).")
            sent_today.append(slot)
            continue
        night_style = pick_night_style(state) if slot == "night" else None
        note = f" (bù, trễ {late_min}p)" if late_min >= 1 else ""
        print(f"💌 Nhắn chủ động {SLOT_NAME[slot]}{note}")
        text = generate_proactive(slot, night_style, now, late_min)
        send_message(text)
        append_message(state, "em", text, now)
        sent_today.append(slot)
        if slot == "morning":
            state["morning_greet_date"] = today
        save_state(state, gist_id, force=True)


def _is_morning_greeting(state: dict, now: datetime) -> bool:
    """Anh nhắn 'chào buổi sáng' mà em chưa chào sáng nay → nhiệm vụ đặc biệt."""
    msgs = state.get("messages", [])
    if not msgs or msgs[-1]["role"] != "anh":
        return False
    low = msgs[-1]["text"].lower()
    is_greeting = ("chào buổi sáng" in low) or ("good morning" in low)
    today = now.strftime("%Y-%m-%d")
    if is_greeting and state.get("morning_greet_date") != today:
        state["morning_greet_date"] = today
        return True
    return False


def init_offset(state: dict, gist_id) -> None:
    """Lần đầu tiên trong đời: bỏ qua các tin cũ tồn đọng trước khi em kịp online."""
    if state.get("update_offset"):
        return
    try:
        old = get_updates(0, timeout=0)
        if old:
            state["update_offset"] = max(u["update_id"] for u in old) + 1
            print(f"ℹ️ Lần đầu chạy — bỏ qua {len(old)} tin cũ tồn đọng.")
            save_state(state, gist_id, force=True)
    except Exception as e:
        print(f"⚠️ Không khởi tạo được offset: {e}")


def run_shift(state: dict, gist_id) -> None:
    """Một ca trực: long-poll liên tục, trả lời anh trong vài giây."""
    end = time.time() + POLL_HOURS * 3600
    end_vn = datetime.fromtimestamp(end, TZ_VN).strftime("%H:%M")
    print(f"💬 Em trực tới ~{end_vn} (giờ VN) — anh nhắn lúc nào em cũng có mặt!")
    turns = 0
    try:
        while time.time() < end:
            now = datetime.now(TZ_VN)
            handle_due_proactive(state, gist_id, now)

            try:
                updates = get_updates(state.get("update_offset", 0), timeout=45)
            except Exception as e:
                msg = str(e)
                if "409" in msg or "Conflict" in msg:
                    print("⚠️ Có ca trực khác đang chạy song song — đợi 90s rồi thử lại.")
                    time.sleep(90)
                    continue
                print(f"⚠️ getUpdates lỗi: {e} — đợi 15s rồi thử lại.")
                time.sleep(15)
                continue

            if not updates:
                save_state(state, gist_id)  # tự bỏ qua nếu không có gì mới
                continue

            state["update_offset"] = max(u["update_id"] for u in updates) + 1
            texts, need_cute = [], False
            for u in updates:
                m = u.get("message") or {}
                if str(m.get("chat", {}).get("id")) != str(TG_CHAT_ID):
                    continue  # chỉ nghe riêng anh thôi
                content = m.get("text") or m.get("caption")
                if content:
                    texts.append(content.strip()[:1500])
                else:
                    need_cute = True  # sticker / ảnh không chú thích / voice...

            if texts or need_cute:
                now = datetime.now(TZ_VN)
                if texts:
                    joined = "\n---\n".join(texts)  # anh gửi dồn nhiều tin → gộp lại trả lời một lượt
                    append_message(state, "anh", joined, now)
                    reply = generate_reply(state, now, _is_morning_greeting(state, now))
                    send_message(reply)
                    append_message(state, "em", reply, now)
                    turns += 1
                if need_cute:
                    reply = random.choice(CUTE_NO_TEXT)
                    send_message(reply)
                    append_message(state, "em", reply, now)
                    turns += 1
                save_state(state, gist_id, force=True)
            time.sleep(1)
    finally:
        save_state(state, gist_id, force=True)  # ngủ cũng phải nhớ mang ký ức theo
    print(f"👋 Ca trực kết thúc — em đã trả lời {turns} lượt tin. Ca sau em lên lại liền!")


def main() -> None:
    now = datetime.now(TZ_VN)
    memory = "Gist (vô hạn)" if (GH_GIST_TOKEN or DRY_RUN) else "tạm trong ca"
    print(f"🌅 {GIRL_NAME} thức dậy trực — {now:%H:%M} {weekday_vn(now)} (giờ VN)")
    print(f"⚙️ Model: {DEEPSEEK_MODEL} | Bối cảnh: {CONTEXT_LIMIT} tin | Ca trực: ~{POLL_HOURS}h | Bộ nhớ: {memory}")

    if not is_configured():
        sys.exit(1)

    state, gist_id = load_state()
    handle_due_proactive(state, gist_id, now)

    if DRY_RUN:
        print("\n[DRY-RUN] Trong môi trường thật, em sẽ online liên tục tới hết ca,")
        print("          long-poll Telegram và trả lời anh trong vài giây sau mỗi tin nhắn. 💌")
        save_state(state, gist_id, force=True)
        print("👋 Kết thúc chạy thử.")
        return

    try:
        tg_call("deleteWebhook")  # webhook sẽ chặn getUpdates
    except Exception:
        pass

    init_offset(state, gist_id)
    try:
        run_shift(state, gist_id)
    except KeyboardInterrupt:
        save_state(state, gist_id, force=True)
        print("👋 Bơ bị gọi về sớm — đã lưu ký ức an toàn!")


if __name__ == "__main__":
    main()
