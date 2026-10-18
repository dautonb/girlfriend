# 💌 Bơ — Bạn gái ảo nhắn tin Telegram

Bot đóng vai **bạn gái** (xưng *em* — gọi anh là *"anh yêu"*), dùng **DeepSeek API** làm bộ não và **Telegram** làm kênh nhắn tin, chạy hoàn toàn tự động trên **GitHub Actions**.

## ✨ Tính năng

| Khung giờ (VN) | Em sẽ nhắn gì |
|---|---|
| **08:00 sáng** | Chào buổi sáng ngọt ngào kèm nickname + lời chúc/động viên cho công việc-học tập + nhắc anh ăn sáng (tối đa 4 câu) |
| **13:00 trưa** | Nhắc anh nghỉ trưa, ăn cơm no, chợp mắt chút xíu |
| **18:00 chiều** | Động viên đẩy nốt việc về đích, hẹn tối kể chuyện |
| **23:00 tối** | *Xen kẽ mỗi ngày*: hôm nay dỗ ngủ ngọt ngào 🥰, mai nhắc ngủ sớm kiểu "không ngủ là em giận đó" 😤 |

Ngoài ra:
- 💬 **Chat hai chiều**: sau mỗi lần nhắn lịch, em online thêm **10 phút** để trả lời nhanh tin anh gửi. Tin anh gửi ngoài khung giờ đó sẽ được trả lời ở lần chạy kế tiếp (trễ tối đa ~3–5 giờ).
- 🌅 Anh nhắn **"Chào buổi sáng"** khi em online → em thực hiện ngay nhiệm vụ chào buổi sáng (nếu chưa chào hôm đó).
- 🧠 **Nhớ 20 tin nhắn gần nhất** — lịch sử được lưu vào `state/chat.json` và bot tự commit vào repo.
- 🎭 **Giữ vai 100%**: tuyệt đối không thừa nhận mình là AI, kể cả khi bị hỏi thẳng.

## 📁 Cấu trúc dự án

```
girlfriend-bot/
├── .github/workflows/girlfriend.yml   # Lịch chạy 4 lần/ngày trên GitHub Actions
├── src/main.py                        # Toàn bộ "linh hồn" của em
├── state/                             # Nhật ký trò chuyện (bot tự ghi)
│   └── README.md
├── requirements.txt                   # Chỉ cần thư viện requests
└── README.md
```

## 🚀 Cài đặt (5 phút)

### Bước 1 — Tạo repo trên GitHub

Tạo một repo mới (được phép để **Private**), rồi đưa toàn bộ thư mục này lên repo:
- Nhớ đặt code ở **nhánh mặc định** (`main`) — lịch cron chỉ chạy trên nhánh mặc định.

### Bước 2 — Thêm 3 Secrets (bắt buộc)

Vào repo → **Settings** → **Secrets and variables** → **Actions** → tab **Secrets** → nút **New repository secret**, tạo lần lượt:

| Name | Secret | Giá trị |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token bot Telegram | Lấy từ [@BotFather](https://t.me/BotFather) khi tạo bot (dạng `123456:ABC-xxx...`) |
| `TELEGRAM_CHAT_ID` | ID cuộc trò chuyện | Nhắn cho bot, rồi mở `https://api.telegram.org/bot<TOKEN>/getUpdates` — tìm `"chat":{"id": 123456789}` |
| `DEEPSEEK_API_KEY` | API key DeepSeek | Tạo tại [platform.deepseek.com](https://platform.deepseek.com) → API Keys |

> 💡 Nếu chưa biết chat_id: nhắn một tin bất kỳ cho bot rồi mở link `getUpdates` trên, giá trị `chat.id` chính là chat_id của anh.

### Bước 3 — Bật Actions

Vào tab **Actions** của repo → nếu có cảnh báo, chọn **"I understand my workflows, go ahead and enable them"**.

### Bước 4 — Chạy thử ngay 🎉

Tab **Actions** → workflow **"💌 Bạn gái nhắn tin"** → **Run workflow** → **Run workflow**.
Vài chục giây sau, tin nhắn đầu tiên sẽ xuất hiện trong Telegram. Sau đó em online 10 phút — anh nhắn gì em trả lời đó!

## ⚙️ Tùy chỉnh (không bắt buộc)

Đặt các giá trị này ở **Settings → Secrets and variables → Actions → tab Variables** → **New repository variable**:

| Variable | Mặc định | Ý nghĩa |
|---|---|---|
| `NICKNAME` | `anh yêu` | Cách em gọi anh |
| `GIRL_NAME` | `Bơ` | Tên của em (vd: Bông, Miu, Sấu...) |
| `POLL_MINUTES` | `10` | Số phút em online sau mỗi lịch để trả lời nhanh |
| `MEMORY_LIMIT` | `20` | Số tin nhắn gần nhất em nhớ |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Model DeepSeek (đặt trong Secret nếu muốn) |

### Đổi giờ nhắn tin

Sửa các dòng `cron` trong `.github/workflows/girlfriend.yml`. Cron dùng **giờ UTC**, giờ VN = UTC **+7**, nên công thức là **giờ VN trừ 7**:

```yaml
schedule:
  - cron: "0 1 * * *"   # 08:00 sáng VN  (1 = 8 - 7)
  - cron: "0 6 * * *"   # 13:00 trưa VN
  - cron: "0 11 * * *"  # 18:00 chiều VN
  - cron: "0 16 * * *"  # 23:00 tối VN
```

Ví dụ muốn sáng 6h30 VN → cron `"30 23 * * *"` (23:30 UTC hôm trước).

## 🧩 Cách hoạt động

```
GitHub Actions cron (4 lần/ngày)
        │
        ▼
python src/main.py
  1. Xác định khung giờ (sáng/trưa/chiều/tối) theo giờ Việt Nam
  2. Đọc bộ nhớ state/chat.json (20 tin gần nhất)
  3. Gọi DeepSeek API với system prompt nhân cách "bạn gái"
  4. Gửi tin qua Telegram Bot API
  5. Online thêm 10 phút — long-poll getUpdates, trả lời tin anh gửi
  6. Commit nhật ký mới vào repo
```

Khi DeepSeek API gặp sự cố, em gửi **tin nhắn dự phòng** được viết sẵn theo đúng nhân cách — nên không bao giờ "im lặng" mất tung đâu 😄

## 🛠 Xử lý sự cố

| Triệu chứng | Nguyên nhân & cách khắc phục |
|---|---|
| Bot không nhắn, Actions báo lỗi Secrets | Kiểm tra lại tên 3 secrets viết đúng chữ hoa, không thừa khoảng trắng |
| Telegram lỗi `409 Conflict` | Bot đang bị webhook chiếm — mở `https://api.telegram.org/bot<TOKEN>/deleteWebhook` rồi chạy lại (script cũng tự gọi deleteWebhook mỗi lần chạy) |
| Tin nhắn trễ 5–15 phút | GitHub cron vốn không đúng giờ tuyệt đối — chuyện bình thường, em vẫn đến, chỉ là "em hơi tắc đường" 😆 |
| Không thấy workflow chạy theo lịch | Repo phải có workflow ở **nhánh mặc định** và Actions đã được bật; repo sleep >60 ngày sẽ bị GitHub tạm dừng lịch — vào Actions chạy lại thủ công là xong |
| Muốn xem em nhắn gì không gửi thật | Chạy tại máy: `DRY_RUN=1 python src/main.py` (không cần key, chỉ in tin nhắn ra màn hình) |
| Bot không trả lời tin anh gửi | Em chỉ online 10 phút sau mỗi lịch; tin ngoài giờ được trả lời ở lần chạy kế tiếp. Nếu anh spam nhiều tin, em gộp lại trả lời một lượt cho tự nhiên |

## 💰 Chi phí & bảo mật

- **GitHub Actions**: Public repo miễn phí không giới hạn; Private repo có 2.000 phút miễn phí/tháng — bot dùng ~20 phút/ngày (≈600 phút/tháng), dư sức.
- **DeepSeek**: deepseek-chat rất rẻ; với mức 4 tin chủ động + vài lượt chat mỗi ngày, chi phí thường dưới 0,05 USD/tháng.
- **Quyền riêng tư**: nhật ký trò chuyện được commit thẳng vào repo (đó là cách em "nhớ"). Nếu muốn kín đáo, hãy để repo **Private**.

## 📝 Ghi chú nhỏ

- Muốn đổi toàn bộ tính cách/giọng điệu? Sửa hàm `base_prompt()` và `slot_task()` trong `src/main.py`.
- Muốn em chủ động nhắn thêm khung giờ khác? Thêm dòng `cron` mới — script tự nhận diện khung giờ theo giờ chạy thực tế.
