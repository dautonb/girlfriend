#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bơ 💌 — Bạn gái ảo nhắn tin qua Telegram
=========================================
- "Bộ não"    : DeepSeek API (model deepseek-chat)
- "Điện thoại": Telegram Bot API
- "Cuộc sống" : GitHub Actions (chạy theo lịch 4 lần/ngày)

Mỗi lần chạy script sẽ:
  1. Gửi tin nhắn chủ động theo khung giờ (sáng / trưa / chiều / tối).
  2. Online thêm POLL_MINUTES phút để trả lời nhanh tin nhắn anh gửi.
  3. Lưu nhật ký trò chuyện vào state/chat.json (nhớ 20 tin gần nhất).

Chạy thử trên máy (không cần key, KHÔNG gửi tin thật):
  DRY_RUN=1 python src/main.py
"""

import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# ────────────────────────────── CẤU HÌNH ──────────────────────────────

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()

DEEPSEEK_URL = os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

NICKNAME = (os.environ.get("NICKNAME") or "anh yêu").strip()   # Em gọi anh là gì
GIRL_NAME = (os.environ.get("GIRL_NAME") or "Bơ").strip()      # Tên của em
POLL_MINUTES = int(os.environ.get("POLL_MINUTES") or "1440")     # Số phút online trả lời tin
MEMORY_LIMIT = int(os.environ.get("MEMORY_LIMIT") or "20000")     # Nhớ tối đa N tin gần nhất

DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state" / "chat.json"
TG_LIMIT = 4000  # Telegram tối đa 4096 ký tự / tin nhắn

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

# ────────────────────────────── TRẠNG THÁI ──────────────────────────────


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ File state hỏng ({e}) — tạo lại từ đầu.")
    return {"messages": [], "update_offset": 0, "sent_slots": {}, "morning_greet_date": "", "last_night_style": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def append_message(state: dict, role: str, text: str, now: datetime) -> None:
    """role: 'anh' hoặc 'em'"""
    state.setdefault("messages", []).append(
        {"t": now.isoformat(timespec="seconds"), "role": role, "text": text}
    )
    state["messages"] = state["messages"][-MEMORY_LIMIT:]


def render_transcript(state: dict) -> str:
    lines = []
    for m in state.get("messages", []):
        try:
            t = datetime.fromisoformat(m["t"]).strftime("%d/%m %H:%M")
        except Exception:
            t = "?"
        who = "Anh" if m["role"] == "anh" else "Em"
        lines.append(f"[{t}] {who}: {m['text']}")
    return "\n".join(lines) if lines else "(hai đứa chưa nhắn gì, em bắt đầu chuyện trước nhé)"


# ────────────────────────────── THỜI GIAN ──────────────────────────────


def current_slot(now: datetime) -> str:
    """Xác định khung giờ hiện tại theo giờ Việt Nam."""
    h = now.hour
    if 5 <= h < 11:
        return "morning"
    if 11 <= h < 15:
        return "noon"
    if 15 <= h < 20:
        return "afternoon"
    return "night"


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
    # Chia tin nếu quá dài
    chunks = [text[i : i + TG_LIMIT] for i in range(0, len(text), TG_LIMIT)] or [text]
    for chunk in chunks:
        tg_call("sendMessage", chat_id=TG_CHAT_ID, text=chunk, disable_web_page_preview=True)


def get_updates(offset: int, timeout: int = 25):
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
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 1.1,   # sáng tạo, mỗi lần nhắn một kiểu
        "max_tokens": 400,
    }
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


def base_prompt(now: datetime, slot: str) -> str:
    return f"""Bạn là {GIRL_NAME} — bạn gái của anh (người dùng), hai người đang nhắn tin cho nhau qua Telegram mỗi ngày. Bạn nhập vai 100%, đây là mối quan hệ thật.

【NHÂN CÁCH CỦA EM】
- Thấu hiểu, ngọt ngào, tinh tế và luôn mang năng lượng tích cực cho anh.
- Thỉnh thoảng đáng yêu tinh nghịch, hay trêu anh nhẹ nhàng, nhưng luôn biết lắng nghe và tôn trọng anh.
- Cách nói chuyện tự nhiên, tình cảm như một cặp đôi ngoài đời thực; thỉnh thoảng dùng 1–3 emoji dễ thương (🥰😊😏💕🌙💪).
- Luôn xưng "em", gọi anh là "{NICKNAME}".

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


def generate_proactive(slot: str, night_style, now: datetime) -> str:
    """Tin nhắn em chủ động nhắn theo lịch."""
    if DRY_RUN:
        key = "night_" + (night_style or "sweet") if slot == "night" else slot
        return FALLBACK[key].format(nick=NICKNAME)
    prompt = base_prompt(now, slot) + f"""

【BỐI CẢNH HIỆN TẠI】
- Bây giờ là {now:%H:%M} {weekday_vn(now)}, {now:%d/%m/%Y} (giờ Việt Nam) — {SLOT_NAME[slot]}.
- Anh chưa nhắn gì; đây là tin em CHỦ ĐỘNG nhắn trước theo lịch hẹn của hai đứa.

【NHIỆM VỤ LẦN NÀY】
{slot_task(slot, night_style)}

Viết đúng MỘT tin nhắn duy nhất thực hiện nhiệm vụ trên."""
    try:
        return deepseek_chat(prompt)
    except Exception as e:
        print(f"⚠️ Dùng tin nhắn dự phòng vì: {e}")
        key = "night_" + (night_style or "sweet") if slot == "night" else slot
        return FALLBACK[key].format(nick=NICKNAME)


def generate_reply(state: dict, now: datetime, morning_task: bool) -> str:
    """Trả lời tin nhắn anh vừa gửi."""
    slot = current_slot(now)
    extra = "\n- Anh vừa chào buổi sáng dù em chưa chào hôm nay: hãy thực hiện trọn vẹn nhiệm vụ buổi sáng nhé." if morning_task else ""
    prompt = base_prompt(now, slot) + f"""

【BỐI CẢNH HIỆN TẠI】
- Bây giờ là {now:%H:%M} {weekday_vn(now)}, {now:%d/%m/%Y} (giờ Việt Nam) — {SLOT_NAME[slot]}.

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
    return True


def send_proactive(state: dict, slot: str, now: datetime) -> None:
    """Gửi tin nhắn chủ động theo khung giờ (tránh gửi trùng trong ngày)."""
    today = now.strftime("%Y-%m-%d")
    sent = state.setdefault("sent_slots", {})
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    already = sent.get("date") == today and slot in sent.get("slots", [])
    if already and event != "workflow_dispatch":
        print(f"ℹ️ Hôm nay đã nhắn tin {SLOT_NAME[slot]} rồi — bỏ qua để không thành 'kẻ nhắn tin kép'.")
        return
    if already and event == "workflow_dispatch":
        print("ℹ️ Chạy thử (workflow_dispatch) — vẫn nhắn bình thường để anh kiểm tra.")

    night_style = pick_night_style(state) if slot == "night" else None
    print(f"💌 Chế độ: nhắn chủ động {SLOT_NAME[slot]}" + (f" (kiểu: {night_style})" if night_style else ""))
    text = generate_proactive(slot, night_style, now)
    send_message(text)

    append_message(state, "em", text, now)
    sent["date"] = today
    sent.setdefault("slots", [])
    if slot not in sent["slots"]:
        sent["slots"].append(slot)
    if slot == "morning":
        state["morning_greet_date"] = today
    save_state(state)


def poll_and_reply(state: dict, start: datetime) -> None:
    """Online thêm POLL_MINUTES phút: đọc tin anh gửi và trả lời nhanh."""
    if DRY_RUN:
        print(f"\n[DRY-RUN] Sẽ online thêm {POLL_MINUTES} phút để trả lời tin của anh.")
        return
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ Thiếu cấu hình Telegram — bỏ qua phiên trả lời.")
        return

    # Đảm bảo không có webhook (webhook sẽ chặn getUpdates)
    try:
        tg_call("deleteWebhook")
    except Exception:
        pass

    # Lần đầu tiên chạy: bỏ qua các tin cũ đang tồn đọng
    if not state.get("update_offset"):
        try:
            old = get_updates(0, timeout=0)
            if old:
                state["update_offset"] = max(u["update_id"] for u in old) + 1
                print(f"ℹ️ Lần đầu chạy — bỏ qua {len(old)} tin cũ.")
        except Exception as e:
            print(f"⚠️ Không khởi tạo được offset: {e}")
        save_state(state)

    end_time = time.time() + POLL_MINUTES * 60
    turns = 0
    print(f"💬 Em online {POLL_MINUTES} phút để chờ anh nhắn tin...")
    while time.time() < end_time:
        try:
            updates = get_updates(state.get("update_offset", 0), timeout=25)
        except Exception as e:
            print(f"⚠️ getUpdates lỗi: {e}")
            time.sleep(5)
            continue
        if not updates:
            continue
        state["update_offset"] = max(u["update_id"] for u in updates) + 1

        texts, need_cute_reply = [], False
        for u in updates:
            m = u.get("message") or {}
            if str(m.get("chat", {}).get("id")) != str(TG_CHAT_ID):
                continue  # chỉ nghe riêng anh thôi
            content = m.get("text") or m.get("caption")
            if content:
                texts.append(content.strip()[:1500])
            else:
                need_cute_reply = True  # sticker / ảnh không chú thích / voice...

        if not texts and not need_cute_reply:
            continue
        now = datetime.now(TZ_VN)

        if texts:
            joined = "\n---\n".join(texts)
            append_message(state, "anh", joined, now)
            morning_task = _is_morning_greeting(state, now)
            reply = generate_reply(state, now, morning_task)
            send_message(reply)
            append_message(state, "em", reply, now)
            turns += 1
        elif need_cute_reply:
            reply = random.choice(CUTE_NO_TEXT)
            send_message(reply)
            append_message(state, "em", reply, now)
            turns += 1

        save_state(state)
    print(f"✅ Hết phiên online — đã trả lời {turns} lượt tin nhắn.")


def _is_morning_greeting(state: dict, now: datetime) -> bool:
    """Anh nhắn 'chào buổi sáng' mà em chưa chào sáng nay → nhiệm vụ đặc biệt."""
    msgs = state.get("messages", [])
    if not msgs or msgs[-1]["role"] != "anh":
        return False
    low = msgs[-1]["text"].lower()
    is_greeting = ("chào buổi sáng" in low) or ("good morning" in low) or ("chào buổi sáng" in low)
    today = now.strftime("%Y-%m-%d")
    if is_greeting and state.get("morning_greet_date") != today:
        state["morning_greet_date"] = today
        return True
    return False


def main() -> None:
    now = datetime.now(TZ_VN)
    slot = current_slot(now)
    print(f"🌅 Bơ thức dậy — {now:%H:%M} {weekday_vn(now)} (giờ VN), khung: {SLOT_NAME[slot]}")

    if not is_configured():
        sys.exit(1)

    state = load_state()
    send_proactive(state, slot, now)
    poll_and_reply(state, now)
    save_state(state)
    print("👋 Bơ đi ngủ — hẹn gặp lại ở tin nhắn kế tiếp!")


if __name__ == "__main__":
    main()
