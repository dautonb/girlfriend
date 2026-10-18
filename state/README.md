# Thư mục này chỉ là bộ nhớ DỰ PHÒNG (fallback).

Từ bản 2.0, nhật ký trò chuyện được lưu vào **Secret Gist** (qua secret
`GH_GIST_TOKEN`) — nhờ vậy repo có thể để public mà tin nhắn vẫn kín đáo.

File `state/chat.json` chỉ được dùng khi:
- Chạy thử trên máy với `DRY_RUN=1`, hoặc
- `GH_GIST_TOKEN` bị thiếu/lỗi — bot vẫn hoạt động nhưng chỉ nhớ tạm trong ca.

File này KHÔNG bao giờ được tự động commit vào repo nữa.
