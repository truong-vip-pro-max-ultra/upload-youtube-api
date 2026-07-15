import os

from yt_uploader import upload_video, UploadError

file_path = "video.mp4"

if not os.path.exists(file_path):
    print(f"Error: Video file '{file_path}' not found!")
    exit(1)


def find_cookie_file() -> str:
    fallback_files = ["cookies.txt", "cookies.json", "cookies/cookies.json", "cookies/cookies.txt"]
    for filename in fallback_files:
        if os.path.exists(filename):
            print(f"[Cookie] Found cookie file: {filename}")
            return filename
    raise RuntimeError("No cookie files found. Please place cookies.json or cookies.txt in the folder.")


def main():
    try:
        cookie_path = find_cookie_file()
    except Exception as e:
        print(f"[Cookie] {e}")
        exit(1)

    title = "Test Upload"
    description = "Uploaded programmatically via pure Python (ported from YouTubei.js)"
    privacy = "PRIVATE"

    try:
        result = upload_video(
            cookie_path,
            file_path,
            title=title,
            description=description,
            privacy=privacy,
        )
        print("=========================================")
        print("UPLOAD SUCCESSFUL!")
        print(f"Video ID: {result.get('videoId')}")
        print("=========================================")
    except UploadError as e:
        print(f"Upload failed: {e}")
        exit(1)
    except Exception as e:
        print(f"Unexpected error during upload: {e}")
        exit(1)


if __name__ == "__main__":
    main()
