"""Pure-Python port of the youtubei.js Studio upload flow.

Thay the hoan toan bgtoken-server (Node.js) cho viec upload video.
Flow giong het youtubei.js `Studio.upload`:
  1. POST https://upload.youtube.com/upload/youtubei   (x-goog-upload-command: start)
  2. POST <upload_url tra ve o buoc 1>                  (upload theo chunk, finalize)
  3. POST https://www.youtube.com/youtubei/v1/upload/createvideo

Auth: SAPISIDHASH tu cookie SAPISID (khong can BotGuard cho flow nay).

Ho tro:
  - Liet ke kenh (kenh chinh + brand channels) tu 1 cookie: `account/accounts_list`
  - Upload len kenh bat ky qua pageId (X-Goog-PageId / onBehalfOfUser)
  - Upload theo chunk -> bao cao tien do, khong load ca file vao RAM
  - Huy giua chung qua callback `should_cancel`
  - QUAN TRONG: dung cookie jar + tu luu cookie xoay vong (SIDCC, __Secure-*PSIDTS...)
    nguoc lai file cookie. Neu cu gui gia tri cu, Google se coi la "cookie replay"
    va huy phien sau vai chuc phut.
"""

import hashlib
import json
import os
import re
import threading
import time
import uuid

from curl_cffi import requests

# Ghi file cookie an toan khi upload da luong (nhieu session cung chia se 1 file)
_SAVE_LOCK = threading.Lock()

YT_BASE = "https://www.youtube.com"
YT_STUDIO = "https://studio.youtube.com"
YT_UPLOAD = "https://upload.youtube.com"

# Trung voi Constants.CLIENTS.WEB cua youtubei.js
CLIENT_NAME = "WEB"
CLIENT_NAME_ID = "1"
CLIENT_VERSION = "2.20250222.10.00"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)

# 8 MiB, boi so cua chunk granularity mac dinh (256 KiB) cua scotty
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024

PRIVACY_LEVELS = ("PRIVATE", "UNLISTED", "PUBLIC")

# GHI CHU (da kiem chung 2026-07): sua metadata SAU khi upload
# (endpoint /youtubei/v1/video_manager/metadata_update, ca protobuf ANDROID lan
# JSON) deu bi YouTube chan bang attestation -> tra ve FAILED_PRECONDITION voi
# MOI truong (title/description/privacy). Do do "lich dang goc" cua YouTube khong
# lam duoc bang Python thuan (can BotGuard/JS runtime). Chi co buoc createvideo
# luc upload la khong bi chan. Vi vay tinh nang lich o day = "hen gio upload":
# app giu video va upload dung gio (can app dang chay).


class UploadError(RuntimeError):
    pass


class UploadCancelled(RuntimeError):
    pass


def _re_search(text: str, key: str):
    match = re.search(rf'"{key}":\s*"([^"]+)"', text)
    return match.group(1) if match else None


def _is_auth_error(exc: Exception) -> bool:
    """Nhan biet loi do phien het han/xac thuc (de retry sau khi lam tuoi)."""
    msg = str(exc).lower()
    return any(k in msg for k in (
        "401", "403", "unauthenticated", "unauthorized",
        "login_required", "not logged in", "authenticate",
    ))


def _extract_rotation_token(text: str):
    """Token cho endpoint RotateCookies = obfuscated page id, nhung trong email
    plusgoogle cua kenh (vd '...-498755448371503134@pages.plusgoogle.com').
    Chi co voi brand channel; kenh ca nhan tra None (khong xoay duoc kieu nay)."""
    m = re.search(r'-(\d{15,20})(?:%40|@)pages\.plusgoogle', text)
    return m.group(1) if m else None


def _walk_find(node, key, found):
    if isinstance(node, dict):
        if key in node:
            found.append(node[key])
        for v in node.values():
            _walk_find(v, key, found)
    elif isinstance(node, list):
        for v in node:
            _walk_find(v, key, found)


# ---------------------------------------------------------------------------
# Cookie store: doc file cookie, nap vao jar, luu cookie xoay vong nguoc lai
# ---------------------------------------------------------------------------

class CookieStore:
    """Quan ly cookie: doc tu file (JSON export / Netscape / chuoi tho),
    nap vao cookie jar cua session, va ghi gia tri moi (do Google xoay vong)
    nguoc lai file sau moi lan dung."""

    def __init__(self, source: str):
        self.path = None
        self._json_entries = None  # giu nguyen entries goc de round-trip file JSON
        content = source
        try:
            if os.path.isfile(source):
                self.path = os.path.abspath(source)
                with open(source, "r", encoding="utf-8") as f:
                    content = f.read()
        except (OSError, ValueError):
            pass
        self.cookies = self._parse(content.strip())
        if not self.cookies:
            raise UploadError("Khong doc duoc cookie nao tu nguon da cho.")

    def _parse(self, content: str) -> list:
        cookies = []
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, list):
                self._json_entries = data
                for entry in data:
                    if entry.get("name"):
                        cookies.append({
                            "name": entry["name"],
                            "value": entry.get("value", ""),
                            "domain": entry.get("domain") or ".youtube.com",
                            "path": entry.get("path") or "/",
                        })
                return cookies
            if isinstance(data, dict):
                self._json_entries = data
                return [
                    {"name": k, "value": str(v), "domain": ".youtube.com", "path": "/"}
                    for k, v in data.items()
                ]
        if "\t" in content:  # Netscape cookies.txt
            for line in content.splitlines():
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    cookies.append({
                        "name": parts[5], "value": parts[6],
                        "domain": parts[0], "path": parts[2],
                    })
            return cookies
        # chuoi "a=b; c=d"
        for pair in content.split(";"):
            if "=" in pair:
                name, _, value = pair.strip().partition("=")
                cookies.append({
                    "name": name, "value": value,
                    "domain": ".youtube.com", "path": "/",
                })
        return cookies

    def apply(self, session: requests.Session):
        for c in self.cookies:
            session.cookies.set(
                c["name"], c["value"],
                domain=c["domain"], path=c["path"], secure=True,
            )

    def cookie_header(self) -> str:
        return "; ".join(f"{c['name']}={c['value']}" for c in self.cookies)

    def save_from(self, session: requests.Session):
        """Ghi gia tri cookie hien tai trong jar (da duoc Google xoay vong)
        nguoc lai file cookie goc. Chi ho tro file JSON export."""
        if not self.path:
            return
        with _SAVE_LOCK:
            self._save_from_locked(session)

    def _save_from_locked(self, session: requests.Session):
        current = {}
        for ck in session.cookies.jar:
            domain = (ck.domain or "").lstrip(".")
            if "youtube" in domain or "google" in domain:
                current[(ck.name, ck.domain)] = ck.value
                current.setdefault(ck.name, ck.value)
        if not current:
            return
        try:
            if isinstance(self._json_entries, list):
                changed = False
                for entry in self._json_entries:
                    new_value = current.get((entry.get("name"), entry.get("domain")))
                    if new_value is None:
                        new_value = current.get(entry.get("name"))
                    if new_value is not None and new_value != entry.get("value"):
                        entry["value"] = new_value
                        changed = True
                if changed:
                    with open(self.path, "w", encoding="utf-8") as f:
                        json.dump(self._json_entries, f, ensure_ascii=False, indent=2)
            elif isinstance(self._json_entries, dict):
                changed = False
                for name in list(self._json_entries.keys()):
                    new_value = current.get(name)
                    if new_value is not None and new_value != self._json_entries[name]:
                        self._json_entries[name] = new_value
                        changed = True
                if changed:
                    with open(self.path, "w", encoding="utf-8") as f:
                        json.dump(self._json_entries, f, ensure_ascii=False, indent=2)
            # Netscape / chuoi tho: khong tu ghi de format khac cua nguoi dung
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Uploader
# ---------------------------------------------------------------------------

def build_context(info: dict) -> dict:
    """Port cua Session#buildContext() + phan gan delegation trong server.js."""
    context = {
        "client": {
            "hl": "en",
            "gl": "US",
            "screenDensityFloat": 1,
            "screenHeightPoints": 1440,
            "screenPixelDensity": 1,
            "screenWidthPoints": 2560,
            "visitorData": info.get("visitor_data") or "",
            "clientName": CLIENT_NAME,
            "clientVersion": CLIENT_VERSION,
            "osName": "Windows",
            "osVersion": "10.0",
            "userAgent": USER_AGENT,
            "platform": "DESKTOP",
            "clientFormFactor": "UNKNOWN_FORM_FACTOR",
            "userInterfaceTheme": "USER_INTERFACE_THEME_LIGHT",
            "originalUrl": YT_BASE,
        },
        "user": {"enableSafetyMode": False, "lockedSafetyMode": False},
        "request": {"useSsl": True, "internalExperimentFlags": []},
    }
    if info.get("delegated_session_id"):
        context["user"]["onBehalfOfUser"] = info["delegated_session_id"]
    if info.get("delegation_context"):
        context["user"]["serializedDelegationContext"] = info["delegation_context"]
    if info.get("channel_id"):
        context["user"]["delegationContext"] = {
            "externalChannelId": info["channel_id"],
            "roleType": {"channelRoleType": "CREATOR_CHANNEL_ROLE_TYPE_OWNER"},
        }
    return context


class YouTubeUploader:
    """Giu 1 phien lam viec (cookie jar + thong tin tai khoan) de upload nhieu video.

    cookie_source: duong dan file cookie (.json export / cookies.txt) hoac
    chuoi cookie tho "a=b; c=d". Neu la file JSON, cookie xoay vong se duoc
    tu dong luu nguoc lai file de phien song lau.
    """

    def __init__(self, cookie_source: str):
        self.store = CookieStore(cookie_source)
        self.session = requests.Session(impersonate="chrome")
        self.store.apply(self.session)
        self.info = None
        self._last_rotate = 0.0

    # ----------------------------------------------------------- auth utils
    def _get_cookie(self, name: str):
        for ck in self.session.cookies.jar:
            if ck.name == name and ck.value:
                return ck.value
        return None

    def _sapisid_hash(self) -> str:
        """Port cua generateSidAuth() trong youtubei.js/utils/Utils.js."""
        sapisid = self._get_cookie("SAPISID") or self._get_cookie("__Secure-3PAPISID")
        if not sapisid:
            raise UploadError("Cookie khong co SAPISID - chua dang nhap hoac cookie sai.")
        timestamp = int(time.time())
        digest = hashlib.sha1(f"{timestamp} {sapisid} {YT_BASE}".encode()).hexdigest()
        return f"SAPISIDHASH {timestamp}_{digest}"

    def _auth_headers(self, identity: dict, origin: str) -> dict:
        """Cac header ma HTTPClient cua youtubei.js gan cho request innertube.
        Cookie do jar cua session tu gui va tu cap nhat khi bi xoay vong."""
        headers = {
            "Accept": "*/*",
            "Accept-Language": "*",
            "X-Goog-Visitor-Id": identity.get("visitor_data") or "",
            "X-Youtube-Client-Version": CLIENT_VERSION,
            "X-Youtube-Client-Name": CLIENT_NAME_ID,
            "User-Agent": USER_AGENT,
            "Origin": origin,
            "Authorization": self._sapisid_hash(),
            "X-Goog-Authuser": "0",
        }
        if identity.get("delegated_session_id"):
            headers["X-Goog-PageId"] = identity["delegated_session_id"]
        return headers

    def save_cookies(self):
        self.store.save_from(self.session)

    def rotate_cookies(self, min_interval: float = 300.0) -> bool:
        """Lam moi cookie qua endpoint RotateCookies cua YouTube (xoay vong
        __Secure-1PSIDTS/3PSIDTS) roi luu nguoc lai file -> phien khong het han
        giua chung upload dai.

        Google rate-limit ~600s/lan (identity.hfcr) nhung van xoay khi goi; ta
        gian toi thieu min_interval de khong goi qua day. Tra True neu da xoay+luu.
        """
        self._require_login()
        token = (self.info or {}).get("rotation_token")
        if not token:
            return False
        now = time.time()
        if now - self._last_rotate < min_interval:
            return False
        headers = {
            "accept": "*/*", "content-type": "application/json",
            "origin": "https://accounts.youtube.com",
            "referer": ("https://accounts.youtube.com/RotateCookiesPage"
                        "?origin=https://studio.youtube.com&yt_pid=62"),
            "user-agent": USER_AGENT,
        }
        try:
            res = self.session.post(
                "https://accounts.youtube.com/RotateCookies",
                headers=headers, data=json.dumps([None, token, 62]), timeout=30,
            )
        except Exception:
            return False
        self._last_rotate = now
        if res.status_code == 200:
            self.save_cookies()
            return True
        return False

    def refresh_session(self) -> bool:
        """Lam tuoi phien khi nghi cookie sap/da het han: re-scrape studio (tu hut
        Set-Cookie moi) + rotate. Dung cho retry khi upload dinh loi xac thuc."""
        try:
            self.login()
        except UploadError:
            return False
        self.rotate_cookies(min_interval=0)
        return True

    # ----------------------------------------------------------- login
    def login(self) -> dict:
        """Scrape YouTube Studio (port getAccountInfo() cua server.js),
        xac nhan cookie con song. Tra ve account info."""
        res = self.session.get(
            YT_STUDIO, headers={"User-Agent": USER_AGENT}, timeout=60
        )
        text = res.text
        info = {
            "channel_id": _re_search(text, "CHANNEL_ID"),
            "delegation_context": _re_search(
                text, "INNERTUBE_CONTEXT_SERIALIZED_DELEGATION_CONTEXT"
            ),
            "delegated_session_id": _re_search(text, "DELEGATED_SESSION_ID"),
            "visitor_data": _re_search(text, "visitorData"),
            # token de RotateCookies (obfuscated page id trong email plusgoogle)
            "rotation_token": _extract_rotation_token(text),
        }
        self.save_cookies()
        if not info.get("channel_id"):
            raise UploadError(
                "Khong lay duoc CHANNEL_ID - cookie het han hoac chua dang nhap. "
                "Hay export cookie moi tu trinh duyet (khi dang dang nhap YouTube)."
            )
        self.info = info
        return info

    def _require_login(self):
        if self.info is None:
            self.login()

    # ----------------------------------------------------------- channels
    def list_channels(self) -> list:
        """Liet ke tat ca kenh (kenh chinh + brand channels) cua cookie nay.

        Port cua AccountManager#getInfo(true) trong youtubei.js
        (endpoint account/accounts_list, ACCOUNTS_LIST_REQUEST_TYPE_CHANNEL_SWITCHER).

        Tra ve list dict: name, handle, photo_url, page_id (None = kenh chinh),
        is_selected.
        """
        self._require_login()
        identity = {"visitor_data": self.info.get("visitor_data")}
        payload = {
            "context": build_context(identity),
            "requestType": "ACCOUNTS_LIST_REQUEST_TYPE_CHANNEL_SWITCHER",
            "callCircumstance": "SWITCHING_USERS_FULL",
        }
        headers = self._auth_headers(identity, YT_BASE)
        headers["Content-Type"] = "application/json"
        res = self.session.post(
            f"{YT_BASE}/youtubei/v1/account/accounts_list?prettyPrint=false&alt=json",
            headers=headers,
            data=json.dumps(payload),
            timeout=60,
        )
        if res.status_code != 200:
            raise UploadError(
                f"accounts_list that bai (HTTP {res.status_code}): {res.text[:300]}"
            )
        self.save_cookies()

        items = []
        _walk_find(res.json(), "accountItemRenderer", items)

        channels = []
        for it in items:
            if not it.get("hasChannel", True):
                continue
            name = (it.get("accountName") or {}).get("simpleText") or ""
            handle = (it.get("channelHandle") or {}).get("simpleText") or ""
            thumbs = (it.get("accountPhoto") or {}).get("thumbnails") or []
            photo_url = thumbs[0].get("url") if thumbs else None
            page_id = None
            tokens = (
                (it.get("serviceEndpoint") or {})
                .get("selectActiveIdentityEndpoint", {})
                .get("supportedTokens", [])
            )
            for token in tokens:
                if "pageIdToken" in token:
                    page_id = token["pageIdToken"].get("pageId")
            channels.append(
                {
                    "name": name,
                    "handle": handle,
                    "photo_url": photo_url,
                    "page_id": page_id,
                    "is_selected": bool(it.get("isSelected")),
                }
            )
        if not channels:
            raise UploadError("Khong tim thay kenh nao trong cookie nay.")
        return channels

    def fetch_bytes(self, url: str) -> bytes:
        """Tai anh dai dien kenh (dung cho GUI)."""
        res = self.session.get(url, timeout=30)
        return res.content

    def _identity(self, page_id) -> dict:
        """Thong tin danh tinh dung cho headers/context theo kenh duoc chon."""
        self._require_login()
        if not page_id or page_id == self.info.get("delegated_session_id"):
            return self.info
        # Upload len brand channel khac kenh mac dinh: chi dung pageId,
        # khong duoc tron channel_id/delegation cua kenh mac dinh vao context.
        return {
            "visitor_data": self.info.get("visitor_data"),
            "delegated_session_id": page_id,
        }

    # ----------------------------------------------------------- upload steps
    def _get_initial_upload_data(self, identity: dict) -> dict:
        """Buoc 1: xin resumable upload URL (Studio#getInitialUploadData)."""
        frontend_upload_id = f"innertube_android:{uuid.uuid4()}:0:v=3,api=1,cf=3"
        payload = {
            "frontendUploadId": frontend_upload_id,
            "deviceDisplayName": "Pixel 6 Pro",
            "fileId": (
                "goog-edited-video://generated?videoFileUri="
                f"content://media/external/video/media/{uuid.uuid4()}"
            ),
            "mp4MoovAtomRelocationStatus": "UNSUPPORTED",
            "transcodeResult": "DISABLED",
            "connectionType": "WIFI",
        }
        headers = self._auth_headers(identity, YT_UPLOAD)
        headers.update(
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "x-goog-upload-command": "start",
                "x-goog-upload-protocol": "resumable",
            }
        )
        res = self.session.post(
            f"{YT_UPLOAD}/upload/youtubei?prettyPrint=false&alt=json",
            headers=headers,
            data=json.dumps(payload),
            timeout=60,
        )
        if res.status_code != 200:
            raise UploadError(
                f"Khong lay duoc upload URL (HTTP {res.status_code}): {res.text[:500]}"
            )
        upload_url = res.headers.get("x-goog-upload-url")
        if not upload_url:
            raise UploadError("Response khong co header x-goog-upload-url")
        granularity = res.headers.get("x-goog-upload-chunk-granularity")
        return {
            "frontend_upload_id": frontend_upload_id,
            "upload_id": res.headers.get("x-guploader-uploadid"),
            "upload_url": upload_url,
            "scotty_resource_id": res.headers.get(
                "x-goog-upload-header-scotty-resource-id"
            ),
            "chunk_granularity": int(granularity) if granularity else 262144,
        }

    def _upload_file_stream(self, upload_url: str, file_path: str,
                            chunk_granularity: int,
                            on_progress=None, should_cancel=None) -> dict:
        """Buoc 2: day file len scotty URL theo chunk (Studio#uploadVideo).

        Dung resumable protocol: moi chunk gui `x-goog-upload-command: upload`
        voi offset, chunk cuoi gui `upload, finalize`. Khong can auth.
        """
        total = os.path.getsize(file_path)
        chunk_size = UPLOAD_CHUNK_SIZE
        if chunk_granularity and chunk_size % chunk_granularity:
            chunk_size = max(chunk_granularity,
                             (chunk_size // chunk_granularity) * chunk_granularity)

        file_name = f"file-{int(time.time() * 1000)}"
        offset = 0
        with open(file_path, "rb") as f:
            while True:
                if should_cancel and should_cancel():
                    raise UploadCancelled("Da huy upload.")
                chunk = f.read(chunk_size)
                is_last = offset + len(chunk) >= total
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "x-goog-upload-command": "upload, finalize" if is_last else "upload",
                    "x-goog-upload-file-name": file_name,
                    "x-goog-upload-offset": str(offset),
                    "User-Agent": USER_AGENT,
                }
                res = self.session.post(
                    upload_url, headers=headers, data=chunk, timeout=3600
                )
                if res.status_code != 200:
                    raise UploadError(
                        f"Upload chunk that bai tai offset {offset} "
                        f"(HTTP {res.status_code}): {res.text[:300]}"
                    )
                offset += len(chunk)
                # Upload dai: dinh ky xoay vong cookie de auth con han cho buoc
                # createvideo o cuoi (chunk khong can auth nhung createvideo can).
                if not is_last:
                    self.rotate_cookies(min_interval=300)
                if on_progress:
                    on_progress(offset, total)
                if is_last:
                    return res.json()

    def _create_video(self, identity: dict, initial_data: dict, upload_result: dict,
                      *, title, description, privacy, is_draft=False,
                      made_for_kids=None) -> dict:
        """Buoc 3: gan metadata va tao video (Studio#setVideoMetadata).

        made_for_kids: None = khong khai bao (mac dinh YouTube coi la NOT_MFK);
        True/False = gui khai bao (best-effort - hien createvideo bo qua field
        nay, khai bao chinh thuc bi chan boi attestation nhu lich goc).
        """
        privacy = (privacy or "PRIVATE").upper()
        if privacy not in PRIVACY_LEVELS:
            raise UploadError(f"Privacy khong hop le: {privacy} (chon {PRIVACY_LEVELS})")
        initial_metadata = {
            "title": {"newTitle": title},
            "description": {"newDescription": description, "shouldSegment": True},
            "privacy": {"newPrivacy": privacy},
            "draftState": {"isDraft": bool(is_draft)},
        }
        if made_for_kids is not None:
            initial_metadata["madeForKids"] = {
                "operation": "MDE_MADE_FOR_KIDS_UPDATE_OPERATION_SET",
                "newMfk": ("MDE_MADE_FOR_KIDS_TYPE_MFK" if made_for_kids
                           else "MDE_MADE_FOR_KIDS_TYPE_NOT_MFK"),
            }
        payload = {
            "context": build_context(identity),
            "resourceId": {
                "scottyResourceId": {"id": upload_result["scottyResourceId"]}
            },
            "frontendUploadId": initial_data["frontend_upload_id"],
            "initialMetadata": initial_metadata,
        }
        headers = self._auth_headers(identity, YT_BASE)
        headers["Content-Type"] = "application/json"
        res = self.session.post(
            f"{YT_BASE}/youtubei/v1/upload/createvideo?prettyPrint=false&alt=json",
            headers=headers,
            data=json.dumps(payload),
            timeout=120,
        )
        if res.status_code != 200:
            raise UploadError(
                f"createvideo that bai (HTTP {res.status_code}): {res.text[:500]}"
            )
        return res.json()

    def upload(self, file_path: str, *, title: str, description: str = "",
               privacy: str = "PRIVATE", page_id: str = None, is_draft: bool = False,
               made_for_kids=None, on_progress=None, should_cancel=None,
               log=print) -> dict:
        """Upload 1 video, tra ve dict co 'videoId'.

        page_id: None = kenh mac dinh cua cookie; nguoc lai la pageId cua
        brand channel lay tu list_channels().
        made_for_kids: None/True/False (xem _create_video).
        on_progress(uploaded_bytes, total_bytes), should_cancel() -> bool.
        """
        if not os.path.exists(file_path):
            raise UploadError(f"Khong tim thay file: {file_path}")

        identity = self._identity(page_id)

        log("[Upload] Buoc 1/3: Xin upload URL...")
        try:
            initial_data = self._get_initial_upload_data(identity)
        except UploadError as e:
            if not _is_auth_error(e):
                raise
            log("[Upload] Cookie loi xac thuc - lam tuoi phien va thu lai...")
            if not self.refresh_session():
                raise
            identity = self._identity(page_id)
            initial_data = self._get_initial_upload_data(identity)

        total = os.path.getsize(file_path)
        log(f"[Upload] Buoc 2/3: Upload {total} bytes...")
        upload_result = self._upload_file_stream(
            initial_data["upload_url"], file_path,
            initial_data["chunk_granularity"],
            on_progress=on_progress, should_cancel=should_cancel,
        )
        if upload_result.get("status") != "STATUS_SUCCESS":
            raise UploadError(f"Xu ly video that bai: {upload_result}")

        log("[Upload] Buoc 3/3: Tao video + gan metadata...")
        try:
            response = self._create_video(
                identity, initial_data, upload_result,
                title=title, description=description, privacy=privacy,
                is_draft=is_draft, made_for_kids=made_for_kids,
            )
        except UploadError as e:
            # File da upload xong (scotty), chi createvideo loi auth -> lam tuoi
            # phien roi thu lai createvideo (khong upload lai file).
            if not _is_auth_error(e):
                raise
            log("[Upload] createvideo loi xac thuc - lam tuoi phien va thu lai...")
            if not self.refresh_session():
                raise
            identity = self._identity(page_id)
            response = self._create_video(
                identity, initial_data, upload_result,
                title=title, description=description, privacy=privacy,
                is_draft=is_draft, made_for_kids=made_for_kids,
            )
        self.save_cookies()
        video_id = response.get("videoId")
        if not video_id:
            raise UploadError(
                f"createvideo khong tra ve videoId: {json.dumps(response)[:500]}"
            )
        return {"success": True, "videoId": video_id, "data": response}


# ---------------------------------------------------------------------------
# API tien dung (dung cho upload_yt.py / script don gian)
# ---------------------------------------------------------------------------

def upload_video(cookie_source: str, video_source, *, title: str,
                 description: str = "", privacy: str = "PRIVATE",
                 is_draft: bool = False, page_id: str = None) -> dict:
    """Upload 1 video.

    cookie_source: duong dan file cookie hoac chuoi cookie tho.
    video_source: duong dan file video (str) hoac bytes.
    """
    uploader = YouTubeUploader(cookie_source)

    print("[Upload] Lay thong tin tai khoan tu YouTube Studio...")
    info = uploader.login()
    print(f"[Upload] Channel ID: {info['channel_id']}")
    if info.get("delegated_session_id"):
        print(f"[Upload] Brand account (delegated): {info['delegated_session_id']}")

    if isinstance(video_source, (bytes, bytearray)):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_source)
            tmp_path = tmp.name
        try:
            return uploader.upload(
                tmp_path, title=title, description=description,
                privacy=privacy, page_id=page_id, is_draft=is_draft,
            )
        finally:
            os.unlink(tmp_path)

    return uploader.upload(
        video_source, title=title, description=description,
        privacy=privacy, page_id=page_id, is_draft=is_draft,
    )


def load_cookie_string(path: str) -> str:
    """Doc file cookie va tra ve chuoi 'name=value; ...' (giu de tuong thich)."""
    return CookieStore(path).cookie_header()
