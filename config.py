
import os


BGTOKEN_SERVER_URL = os.getenv("BGTOKEN_SERVER_URL", "http://localhost:4416")

COOKIES_DIR = os.getenv("COOKIES_DIR", "cookies")
VIDEOS_DIR = os.getenv("VIDEOS_DIR", "videos")
METADATA_FILE = os.getenv("METADATA_FILE", "videos.json")


MAX_WORKERS = int(os.getenv("MAX_WORKERS", "5"))
DEFAULT_PRIVACY = os.getenv("DEFAULT_PRIVACY", "PRIVATE")
UPLOAD_AS_SHORT = False
RETRY_COUNT = int(os.getenv("RETRY_COUNT", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))
DELAY_BETWEEN_UPLOADS = (2, 8)


TOKEN_REFRESH_INTERVAL = 1800

CHROME_VERSION = "148"
CHROME_FULL_VERSION = "148.0.7778.260"

DEFAULT_HEADERS = {
    'accept': '*/*',
    'accept-language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
    'origin': 'https://studio.youtube.com',
    'sec-ch-ua': f'"Chromium";v="{CHROME_VERSION}", "Google Chrome";v="{CHROME_VERSION}", "Not/A)Brand";v="99"',
    'sec-ch-ua-arch': '"x86"',
    'sec-ch-ua-bitness': '"64"',
    'sec-ch-ua-form-factors': '"Desktop"',
    'sec-ch-ua-full-version': f'"{CHROME_FULL_VERSION}"',
    'sec-ch-ua-full-version-list': f'"Chromium";v="{CHROME_FULL_VERSION}", "Google Chrome";v="{CHROME_FULL_VERSION}", "Not/A)Brand";v="99.0.0.0"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-model': '""',
    'sec-ch-ua-platform': '"Windows"',
    'sec-ch-ua-platform-version': '"10.0.0"',
    'sec-ch-ua-wow64': '?1',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36',
}
