"""Verify lịch gốc YouTube (BotGuard ctx) — chạy 1 lần với cookie sống.
Upload 1 clip nhỏ PRIVATE, đặt lịch công khai, đọc lại để xác nhận, rồi hoàn tác.

Chạy:  python verify_native.py [pageId]
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yt_uploader import YouTubeUploader
import native_schedule as ns

PAGE = sys.argv[1] if len(sys.argv) > 1 else "116702359715477581962"  # Suối Thiền An Nhiên
# clip nhỏ để test (đã cắt sẵn trong scratchpad); fallback video.mp4
SCRATCH = r"C:\Users\TRUONG~1\AppData\Local\Temp\claude\C--Users-truongjae-Desktop-vibe-code-upload-youtube\36fc8986-626d-4239-a006-1c9ef7494244\scratchpad"
CLIP = None
for c in [os.path.join(SCRATCH, "clip_a.mp4"), "video.mp4", os.path.join("videos", "video.mp4")]:
    if os.path.exists(c):
        CLIP = c
        break
if not CLIP:
    print("Không tìm thấy file video để test."); sys.exit(1)

up = YouTubeUploader("cookies/cookies.json")
up.login()
print("login OK. Node/BotGuard sẵn sàng:", ns.botguard_available())

print(f"Upload clip test (PRIVATE) lên page {PAGE}...")
res = up.upload(CLIP, title="native-sched-verify", description="test lịch gốc",
                privacy="PRIVATE", page_id=PAGE, log=lambda m: None)
VID = res["videoId"]
print("uploaded:", VID)
time.sleep(3)
print("state trước:", json.dumps(ns.read_video_state(up, VID, PAGE), ensure_ascii=False))

publish_at = int(time.time()) + 2 * 24 * 3600
print("Sẽ lên lịch công khai lúc:", time.strftime("%d/%m/%Y %H:%M", time.localtime(publish_at)),
      f"(epoch {publish_at})")

resp = ns.schedule_video(up, VID, publish_at, page_id=PAGE, privacy="PUBLIC")
print("schedule response:", json.dumps(resp, ensure_ascii=False)[:200])
time.sleep(3)
after = ns.read_video_state(up, VID, PAGE)
print("state sau :", json.dumps(after, ensure_ascii=False))
got = after.get("timePublishedSeconds")
print(f"\n==> target={publish_at} | timePublishedSeconds đọc được={got}")
if got and abs(int(got) - publish_at) < 120:
    print("==> ✅ LỊCH GỐC HOẠT ĐỘNG: video sẽ tự công khai đúng giờ (tắt máy vẫn đăng).")
else:
    print("==> ⚠️ Chưa khớp — cần chỉnh cấu trúc scheduledPublishing.")

print(f"\nVIDEO test: {VID} (đang PRIVATE + đặt lịch). Bạn có thể xóa nếu muốn.")
