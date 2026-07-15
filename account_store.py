"""Quan ly NHIEU tai khoan (moi cookie = 1 account), giong upload-facebook-reels.

Moi account luu cookie rieng o cookies/accounts/<id>.json de co che xoay vong
(CookieStore.save_from) hoat dong doc lap tung account. Index metadata (ten, trang
thai, danh sach kenh da cache) o cookies/accounts.json.

Account co the co NHIEU kenh (kenh chinh + brand channel) — dung chung 1 cookie.
"""

import json
import os
import time
import uuid

from yt_uploader import CookieStore, YouTubeUploader

STATUS_UNKNOWN = "UNKNOWN"
STATUS_ALIVE = "ALIVE"
STATUS_DEAD = "DEAD"
STATUS_CHECKING = "CHECKING"

_LOGIN_COOKIES = ("SAPISID", "__Secure-3PAPISID", "SID", "__Secure-1PSID")


def cookie_signature(cookies: list) -> str:
    """Chu ky nhan dang account = gia tri SAPISID (cung account => cung SAPISID)."""
    by_name = {c.get("name"): c.get("value") for c in cookies}
    for name in ("SAPISID", "__Secure-3PAPISID", "SID"):
        if by_name.get(name):
            return f"{name}:{by_name[name]}"
    return ""


def has_login_cookie(cookies: list) -> bool:
    names = {c.get("name") for c in cookies}
    return bool(names & set(_LOGIN_COOKIES))


class Account:
    """Mot tai khoan Google (1 cookie), co the co nhieu kenh."""

    def __init__(self, data: dict):
        self.id = data["id"]
        self.name = data.get("name") or "(chưa kiểm tra)"
        self.cookie_path = data["cookie_path"]
        self.signature = data.get("signature", "")
        self.status = data.get("status", STATUS_UNKNOWN)
        self.channels = data.get("channels", [])  # [{name,handle,page_id,is_selected}]
        self.last_check = data.get("last_check", "")

    def to_dict(self) -> dict:
        # bo 'photo' (bytes, khong JSON-serializable) — anh giu trong RAM tung phien
        clean = [{k: v for k, v in c.items() if k != "photo"} for c in self.channels]
        return {
            "id": self.id, "name": self.name, "cookie_path": self.cookie_path,
            "signature": self.signature, "status": self.status,
            "channels": clean, "last_check": self.last_check,
        }

    @property
    def channel_count(self) -> int:
        return len(self.channels)


class AccountStore:
    """Danh sach account ben vung (index JSON + file cookie rieng tung account)."""

    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.dir = os.path.join(base_dir, "cookies", "accounts")
        self.index_path = os.path.join(base_dir, "cookies", "accounts.json")
        os.makedirs(self.dir, exist_ok=True)
        self.accounts = self._load()

    def _load(self) -> list:
        if not os.path.exists(self.index_path):
            return []
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [Account(d) for d in data if d.get("id") and d.get("cookie_path")]
        except (OSError, ValueError):
            return []

    def save(self):
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump([a.to_dict() for a in self.accounts], f,
                      ensure_ascii=False, indent=2)

    def find_by_signature(self, sig: str):
        for a in self.accounts:
            if sig and a.signature == sig:
                return a
        return None

    def add_cookies(self, cookies: list, name: str = "") -> tuple:
        """Them 1 account tu list cookie (da parse). Tra ve (account, created).

        Neu trung SAPISID voi account cu -> cap nhat cookie account do (created=False).
        """
        sig = cookie_signature(cookies)
        existing = self.find_by_signature(sig) if sig else None
        if existing:
            self._write_cookie_file(existing.cookie_path, cookies)
            return existing, False
        acc_id = uuid.uuid4().hex[:8]
        path = os.path.join(self.dir, f"{acc_id}.json")
        self._write_cookie_file(path, cookies)
        acc = Account({
            "id": acc_id, "name": name or "(chưa kiểm tra)",
            "cookie_path": path, "signature": sig, "status": STATUS_UNKNOWN,
            "channels": [], "last_check": "",
        })
        self.accounts.append(acc)
        self.save()
        return acc, True

    def add_from_text(self, text: str) -> tuple:
        """Parse chuoi cookie (JSON/netscape/tho) -> them account. Raise neu sai."""
        store = CookieStore(text)
        if not has_login_cookie(store.cookies):
            raise ValueError("Thiếu cookie đăng nhập (SAPISID/SID).")
        return self.add_cookies(store.cookies)

    @staticmethod
    def _write_cookie_file(path: str, cookies: list):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

    def remove(self, acc: Account):
        try:
            if os.path.exists(acc.cookie_path):
                os.remove(acc.cookie_path)
        except OSError:
            pass
        self.accounts = [a for a in self.accounts if a.id != acc.id]
        self.save()

    def set_result(self, acc: Account, *, name: str = None, channels: list = None,
                   status: str = None):
        if name is not None:
            acc.name = name
        if channels is not None:
            acc.channels = channels
        if status is not None:
            acc.status = status
        acc.last_check = time.strftime("%d/%m %H:%M")
        self.save()


def check_account(acc: Account) -> dict:
    """Dang nhap + liet ke kenh cho 1 account. Tra ve {name, channels, status}.

    Chay trong thread (khong dung Qt). Anh dai dien tai kem (bytes) de GUI dung.
    """
    uploader = YouTubeUploader(acc.cookie_path)
    uploader.login()
    channels = uploader.list_channels()
    for ch in channels:
        ch["photo"] = None
        if ch.get("photo_url"):
            try:
                ch["photo"] = uploader.fetch_bytes(ch["photo_url"])
            except Exception:
                pass
    # ten account = kenh dang chon / kenh chinh
    main = next((c for c in channels if c.get("is_selected")), channels[0] if channels else None)
    name = main["name"] if main else acc.name
    return {"name": name, "channels": channels, "status": STATUS_ALIVE}
