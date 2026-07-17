# Changelog

## 2026-07-17

### Thêm mới
- **Kiểm tra độ dài tiêu đề (tối đa 100 ký tự)** — đúng giới hạn của YouTube:
  - Sửa 1 video: ô tiêu đề chặn gõ quá 100 ký tự, có bộ đếm `n/100` (đỏ khi chạm giới hạn), bấm **Lưu** mà vượt sẽ báo lỗi và không lưu.
  - Đặt tiêu đề hàng loạt (`{n}`/`{name}`): **không cắt** tiêu đề — chỉ bắn cảnh báo số tiêu đề vượt 100 ký tự để tự sửa lại trước khi upload.

## 2026-07-15

### Thêm mới
- **Port sang Python thuần**: `yt_uploader.py` thay hoàn toàn sidecar Node cho việc upload (login scrape studio, `accounts_list` liệt kê kênh, upload chunk resumable qua scotty, `createvideo`). Auth SAPISIDHASH, không cần BotGuard.
- **GUI PySide6** (`app.py`): giao diện tối, 2 tab.
- **Quản lý nhiều tài khoản** (`account_store.py`): mỗi cookie = 1 tài khoản, index `cookies/accounts.json` + file cookie riêng mỗi tài khoản (rotation độc lập), chống trùng theo SAPISID, lưu bền qua phiên.
- **Mô hình kênh-là-chính** (giống upload-facebook-reels): bảng Upload = danh sách kênh, gán N video vào từng kênh; checkbox chọn nhiều + thao tác trên dòng đã tích/bôi đen.
- **Thao tác hàng loạt**: Gán video / Tiêu đề (`{n}`,`{name}`) / Mô tả cho nhiều kênh; popup "Quản lý video" + "Chi tiết video" ô lớn.
- **Đa luồng**: song song giữa các tài khoản, tuần tự trong 1 tài khoản (khóa theo cookie).
- **Dán cookie JSON** popup (thay chọn file), lưu ngầm dạng JSON array để rotation chạy.
- **Chế độ hiển thị + đối tượng (trẻ em)** chung/ghi đè; **hẹn giờ đăng phía app**.
- **Cookie rotation tự động**: `RotateCookies` (token = obfuscated page id từ email plusgoogle), nút "Làm mới cookie" thủ công, tự rotate mỗi ~5 phút khi upload dài, retry khi lỗi xác thực (không upload lại file).

### Kiểm chứng / Giới hạn
- Xác nhận `metadata_update` (lịch gốc, made-for-kids, thumbnail) bị **attestation + reauth session-risk** chặn — cả JSON client-62 lẫn Android-protobuf, kể cả cookie mới sạch. Không dùng được bằng cookie thuần.
- Cookie rotation đã verify end-to-end: rotate → PSIDTS đổi → lưu file → re-login vẫn sống.
