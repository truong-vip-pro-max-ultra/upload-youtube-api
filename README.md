# YT Batch Uploader

Công cụ upload video YouTube hàng loạt bằng **cookie** (không dùng YouTube Data API), viết bằng **Python thuần** để dễ đóng gói `.exe`. Có GUI (PySide6) quản lý **nhiều tài khoản**, mỗi tài khoản **nhiều kênh**, gán video cho từng kênh và upload song song.

> ⚠️ Dùng cho mục đích cá nhân/được phép. Cookie là thông tin đăng nhập — **không chia sẻ, không commit lên git** (đã có `.gitignore`).

## Tính năng

- **Quản lý nhiều tài khoản** (mỗi cookie = 1 tài khoản), lưu bền qua các phiên, mỗi tài khoản có file cookie riêng để cookie rotation hoạt động độc lập.
- **Nhiều kênh / tài khoản**: sau khi "Kiểm tra & tải kênh", mọi kênh (kênh chính + brand channel) hiện thành danh sách.
- **Mô hình kênh-là-chính** (giống upload-facebook-reels): bảng là danh sách kênh, gán N video vào từng kênh.
- **Thao tác hàng loạt**: gán video / tiêu đề (`{n}`, `{name}`) / mô tả cho nhiều kênh cùng lúc; chọn nhiều bằng checkbox hoặc bôi đen.
- **Sửa chi tiết từng video** trong popup ô lớn (tiêu đề + mô tả nhiều dòng).
- **Chế độ hiển thị** (Riêng tư / Không công khai / Công khai) và **đối tượng** (không dành cho trẻ em) — đặt chung hoặc ghi đè riêng.
- **Upload đa luồng**: song song giữa các tài khoản, tuần tự trong một tài khoản (an toàn).
- **Hẹn giờ đăng phía app**: giữ video, đến giờ mới upload (máy phải mở).
- **Tự làm mới cookie** (`RotateCookies`): tránh hết hạn giữa chừng upload; nút "Làm mới cookie" thủ công + tự động rotate khi upload dài + retry khi lỗi xác thực.

## Cài đặt

```bash
pip install -r requirements.txt
python app.py
```

Yêu cầu: Python 3.10+, `curl_cffi`, `PySide6`.

## Cách dùng

1. **Tab Tài khoản** → "Dán cookie JSON" (export từ Cookie-Editor) hoặc "Thêm từ file" → mỗi cookie 1 tài khoản.
2. Tích chọn tài khoản → **"Kiểm tra & tải kênh"** để lấy tên + danh sách kênh.
3. **Tab Upload video** → tích chọn các kênh → **"Gán video → đã chọn"** (chọn N file) → mỗi kênh nhận N video.
4. (Tùy chọn) "Tiêu đề → …", "Mô tả → …" hàng loạt; nháy đúp kênh để "Quản lý video…"; nháy đúp video để sửa ô lớn.
5. Chọn chế độ hiển thị / đối tượng / số luồng / hẹn giờ ở panel trái.
6. **"Bắt đầu upload"**.

Ví dụ *"10 kênh đều đăng 5 video"*: tích 10 kênh → "Gán video → đã chọn" chọn 5 file → Bắt đầu (50 lượt).

## Cấu trúc

| File | Vai trò |
|---|---|
| `yt_uploader.py` | Lõi upload thuần Python (login, liệt kê kênh, upload chunk, cookie rotation, retry) |
| `account_store.py` | Quản lý nhiều tài khoản (index + file cookie riêng) |
| `app.py` | GUI PySide6 (2 tab: Tài khoản, Upload video) |
| `native_schedule.py` | Nghiên cứu lịch gốc/attestation (xem Giới hạn) |
| `bgtoken-server/` | Sidecar Node (BotGuard) — chỉ phục vụ nghiên cứu, không cần cho upload |

## Cookie rotation (chống hết hạn giữa upload)

Cookie `__Secure-1PSIDTS/3PSIDTS` hết hạn nhanh. App tự xoay vòng:
- **Save-back**: sau mỗi request, cookie xoay vòng được ghi lại file.
- **RotateCookies**: gọi `accounts.youtube.com/RotateCookies` với token là *obfuscated page id* (trích từ email `…@pages.plusgoogle.com` trong trang studio). Nút "Làm mới cookie" thủ công + tự động mỗi ~5 phút khi upload dài.
- **Retry**: bước tạo video gặp lỗi xác thực → làm tươi phiên → thử lại (không upload lại file).

## Giới hạn đã biết

- **Lịch gốc YouTube / Made-for-Kids chính thức / Thumbnail** đi qua endpoint `metadata_update` bị **attestation + reauth (đăng nhập lại)** chặn — không làm được bằng cookie thuần (đã kiểm chứng kỹ, kể cả đường Android-protobuf). Dùng "hẹn giờ phía app" thay thế.
- Upload dồn dập nhiều tài khoản/kênh dễ bị Google gắn cờ phiên — nên để luồng thấp và giãn cách.

## Đóng gói exe

```bash
pyinstaller --onefile --windowed --collect-all curl_cffi app.py
```
