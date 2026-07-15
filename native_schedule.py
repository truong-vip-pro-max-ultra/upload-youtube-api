"""Lich dang GOC cua YouTube (video len san, YouTube tu cong khai dung gio,
ke ca khi tat may).

Khac voi "hen gio upload" phia app, cach nay dat scheduledPublishing that su
tren YouTube. Endpoint studio metadata_update bi chan bang attestation, nen
BAT BUOC co ctx token tu BotGuard -> can 1 sidecar Node toi thieu
(bgtoken-server/botguard_cli.js) chi de giai BotGuard va lay ctx.

Flow:
  1. scrape_account_info(): lay eats + channel_id + serialized_delegation tu Studio
  2. solve_attestation(): goi Node botguard_cli.js -> challenge + webResponse (d=62)
  3. schedule_publish(): goi studio metadata_update voi ctx + scheduledPublishing
"""

import codecs
import hashlib
import json
import os
import random
import re
import shutil
import string
import subprocess
import time

from yt_uploader import USER_AGENT, YT_STUDIO, UploadError

# Thu muc chua botguard_cli.js + node_modules (bgutils-js, jsdom, youtubei.js)
BOTGUARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bgtoken-server")
BOTGUARD_CLI = "botguard_cli.js"


def find_node() -> str:
    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        # cho phep dat node.exe canh sidecar (khi dong goi kem)
        local = os.path.join(BOTGUARD_DIR, "node.exe")
        if os.path.exists(local):
            return local
        raise UploadError(
            "Khong tim thay Node.js. Lich goc YouTube can Node de giai BotGuard. "
            "Cai Node (https://nodejs.org) hoac bo tinh nang lich goc, dung 'hen gio upload'."
        )
    return node


def botguard_available() -> bool:
    try:
        find_node()
    except UploadError:
        return False
    return os.path.exists(os.path.join(BOTGUARD_DIR, BOTGUARD_CLI)) and \
        os.path.isdir(os.path.join(BOTGUARD_DIR, "node_modules"))


def _rs(text: str, key: str):
    m = re.search(r'"' + key + r'":"(.*?)"', text)
    if not m:
        return None
    try:
        return codecs.decode(m.group(1), "unicode_escape")
    except Exception:
        return m.group(1)


def scrape_account_info(uploader, page_id: str = None) -> dict:
    """Scrape trang Studio (dung X-Goog-PageId de dung kenh) lay eats + delegation."""
    headers = {"User-Agent": USER_AGENT}
    if page_id:
        headers["X-Goog-PageId"] = page_id
    res = uploader.session.get(YT_STUDIO, headers=headers, timeout=60)
    text = res.text
    uploader.save_cookies()
    # consistencyTokenJars nhung trong HTML - can cho reauth (get_web_reauth_url/grst)
    jars = []
    mj = re.search(r'"consistencyTokenJars":(\[\{.*?\}\])', text)
    if mj:
        try:
            jars = json.loads(mj.group(1))
        except Exception:
            jars = []
    info = {
        "eats": _rs(text, "EATS"),
        "channel_id": _rs(text, "CHANNEL_ID"),
        "delegated_session_id": page_id or _rs(text, "DELEGATED_SESSION_ID"),
        "serialized_delegation_context": _rs(
            text, "INNERTUBE_CONTEXT_SERIALIZED_DELEGATION_CONTEXT"),
        "consistency_token_jars": jars,
    }
    if not info["eats"] or not info["channel_id"]:
        raise UploadError("Khong scrape duoc eats/channel_id (cookie het han?).")
    return info


def _studio_sapisidhash(uploader) -> str:
    sap = uploader._get_cookie("SAPISID") or uploader._get_cookie("__Secure-3PAPISID")
    ts = int(time.time())
    return f"{ts}_{hashlib.sha1(f'{ts} {sap} {YT_STUDIO}'.encode()).hexdigest()}"


def _studio_context_client() -> dict:
    return {"clientName": 62, "clientVersion": "1.20260709.05.00",
            "hl": "vi", "gl": "VN", "experimentsToken": "",
            "utcOffsetMinutes": 420,
            "userInterfaceTheme": "USER_INTERFACE_THEME_LIGHT",
            "screenWidthPoints": 1278, "screenHeightPoints": 927,
            "screenPixelDensity": 1, "screenDensityFloat": 1}


def _studio_headers(uploader, page_id: str = None) -> dict:
    headers = {
        "Accept": "*/*",
        "Authorization": f"SAPISIDHASH {_studio_sapisidhash(uploader)}",
        "Content-Type": "application/json", "Origin": YT_STUDIO,
        "User-Agent": USER_AGENT, "X-Goog-Authuser": "0",
    }
    if page_id:
        headers["X-Goog-PageId"] = page_id
    return headers


def att_get(uploader, engagement_type: str, ids: list = None,
            page_id: str = None) -> dict:
    """Goi /att/get tren Studio (client 62).

    Tra ve dict: challenge, program, global_name, interpreter_url.
    Response co the dung key 'bgChallenge' (co globalName) hoac 'botguardData'
    (interpreterSafeUrl, khong globalName -> mac dinh 'trayride').
    """
    body = {"engagementType": engagement_type, "context": {"client": _studio_context_client()}}
    if ids:
        body["ids"] = ids
    res = uploader.session.post(
        f"{YT_STUDIO}/youtubei/v1/att/get?alt=json",
        headers=_studio_headers(uploader, page_id), data=json.dumps(body), timeout=60,
    )
    uploader.save_cookies()
    if res.status_code != 200:
        raise UploadError(f"/att/get that bai (HTTP {res.status_code}): {res.text[:300]}")
    data = res.json()
    if not data.get("challenge"):
        raise UploadError(f"/att/get thieu challenge: {json.dumps(data)[:200]}")
    bg = data.get("bgChallenge") or data.get("botguardData")
    if not bg or not bg.get("program"):
        raise UploadError(f"/att/get thieu program: {json.dumps(data)[:200]}")
    iu = bg.get("interpreterUrl") or bg.get("interpreterSafeUrl") or {}
    interpreter_url = iu.get("privateDoNotAccessOrElseTrustedResourceUrlWrappedValue")
    content_binding = {"c": data["challenge"], "e": engagement_type}
    if ids and ids[0].get("externalChannelId"):
        content_binding["externalChannelId"] = ids[0]["externalChannelId"]
    return {
        "challenge": data["challenge"],
        "program": bg["program"],
        "global_name": bg.get("globalName") or "trayride",
        "interpreter_url": interpreter_url,
        "content_binding": content_binding,
    }


def solve_program(challenge_data: dict, timeout: int = 120, retries: int = 3) -> str:
    """Giai 1 program BotGuard qua Node VM -> webResponse (snapshot bound challenge)."""
    node = find_node()
    payload = {
        "program": challenge_data["program"],
        "globalName": challenge_data["global_name"],
        "interpreterUrl": challenge_data["interpreter_url"],
        "contentBinding": challenge_data["content_binding"],
    }
    last_err = None
    for _ in range(max(1, retries)):
        try:
            proc = subprocess.run(
                [node, BOTGUARD_CLI],
                input=json.dumps(payload),
                cwd=BOTGUARD_DIR,
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            last_err = "BotGuard VM (Node) qua thoi gian."
            continue
        out = (proc.stdout or "").strip()
        if not out:
            last_err = f"BotGuard VM khong tra ket qua. stderr: {proc.stderr[:300]}"
            continue
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            last_err = f"BotGuard VM tra ve khong hop le: {out[:300]}"
            continue
        if not data.get("ok"):
            last_err = f"BotGuard VM loi: {data.get('error')}"
            if "timed out" in (data.get("error") or "").lower():
                continue
            raise UploadError(last_err)
        return data["webResponse"]
    raise UploadError(last_err or "BotGuard VM that bai.")


def _studio_user(info_account: dict, page_id: str) -> dict:
    user = {}
    if page_id:
        user["onBehalfOfUser"] = page_id
    if info_account and info_account.get("serialized_delegation_context"):
        user["serializedDelegationContext"] = info_account["serialized_delegation_context"]
    if info_account and info_account.get("channel_id"):
        user["delegationContext"] = {
            "externalChannelId": info_account["channel_id"],
            "roleType": {"channelRoleType": "CREATOR_CHANNEL_ROLE_TYPE_OWNER"},
        }
    return user


def att_esr(uploader, challenge: str, botguard_response: str,
            page_id: str = None, info_account: dict = None) -> str:
    """Goi /att/esr voi challenge + botguardResponse -> ctx (sessionInfo.token)."""
    context = {"client": _studio_context_client()}
    user = _studio_user(info_account, page_id)
    if user:
        context["user"] = user
    body = {"context": context,
            "challenge": challenge, "botguardResponse": botguard_response}
    res = uploader.session.post(
        f"{YT_STUDIO}/youtubei/v1/att/esr?alt=json",
        headers=_studio_headers(uploader, page_id), data=json.dumps(body), timeout=60,
    )
    uploader.save_cookies()
    if res.status_code != 200:
        raise UploadError(f"/att/esr that bai (HTTP {res.status_code}): {res.text[:300]}")
    data = res.json()
    if not data.get("ctx"):
        raise UploadError(f"/att/esr khong tra ctx: {json.dumps(data)[:200]}")
    return data["ctx"]


def get_web_reauth_url(uploader, ivctx: str, challenge: str,
                       botguard_response: str, *, page_id: str = None,
                       info_account: dict = None) -> tuple:
    """Buoc reauth 1 (COLD_LOAD, khong can mat khau): dung BotGuard lam bang chung.

    ivctx = ctx tra ve tu att/esr; challenge/botguardResponse = nhanh
    CREATOR_STUDIO_ACTION. Tra ve (encodedReauthProofToken, sessionRiskCtx).
    """
    request = {"returnLogEntry": True, "internalExperimentFlags": [],
               "eats": info_account["eats"],
               "consistencyTokenJars": info_account.get("consistency_token_jars", [])}
    context = {"client": _studio_context_client(), "request": request}
    user = _studio_user(info_account, page_id)
    if user:
        context["user"] = user
    body = {
        "context": context,
        "continueUrl": f"{YT_STUDIO}/reauth",
        "flow": "REAUTH_FLOW_YT_STUDIO_COLD_LOAD",
        "ivctx": ivctx,
        "challenge": challenge,
        "botguardResponse": botguard_response,
    }
    res = uploader.session.post(
        f"{YT_STUDIO}/youtubei/v1/security/get_web_reauth_url?alt=json",
        headers=_studio_headers(uploader, page_id), data=json.dumps(body), timeout=60,
    )
    uploader.save_cookies()
    if res.status_code != 200:
        raise UploadError(
            f"get_web_reauth_url that bai (HTTP {res.status_code}): {res.text[:300]}")
    data = res.json()
    token = data.get("encodedReauthProofToken")
    risk = data.get("sessionRiskCtx")
    if not token or not risk:
        raise UploadError(f"get_web_reauth_url thieu token: {json.dumps(data)[:200]}")
    return token, risk


def ars_grst(uploader, session_risk_ctx: str, encoded_reauth_proof_token: str, *,
             page_id: str = None, info_account: dict = None) -> str:
    """Buoc reauth 2: doi reauthProofToken -> sessionToken (dung cho
    context.request.sessionInfo.token cua metadata_update)."""
    request = {"returnLogEntry": True, "internalExperimentFlags": [],
               "eats": info_account["eats"],
               "reauthRequestInfo": {
                   "encodedReauthProofToken": encoded_reauth_proof_token},
               "consistencyTokenJars": info_account.get("consistency_token_jars", [])}
    context = {"client": _studio_context_client(), "request": request}
    user = _studio_user(info_account, page_id)
    if user:
        context["user"] = user
    body = {"context": context, "ctx": session_risk_ctx}
    res = uploader.session.post(
        f"{YT_STUDIO}/youtubei/v1/ars/grst?alt=json",
        headers=_studio_headers(uploader, page_id), data=json.dumps(body), timeout=60,
    )
    uploader.save_cookies()
    if res.status_code != 200:
        raise UploadError(f"ars/grst that bai (HTTP {res.status_code}): {res.text[:300]}")
    data = res.json()
    if not data.get("sessionToken"):
        raise UploadError(f"ars/grst khong tra sessionToken: {json.dumps(data)[:200]}")
    return data["sessionToken"]


def solve_attestation(uploader, info_account: dict, page_id: str = None) -> dict:
    """Luong day du (theo HAR) de lay attestation + reauth cho metadata_update:

      1. att/get UNBOUND -> program_1 -> snapshot_1  (attestationResponseData)
      2. att/get CREATOR_STUDIO_ACTION + channelId -> program_2 -> snapshot_2
      3. att/esr(challenge_2, snapshot_2) -> ivctx
      4. get_web_reauth_url(ivctx, challenge_2, snapshot_2) -> reauthProofToken + riskCtx
      5. ars/grst(riskCtx, reauthProofToken) -> sessionToken  (sessionInfo.token)

    Tra ve dict: challenge (=challenge_1), webResponse (=snapshot_1),
    ctx (=sessionToken tu grst).
    """
    channel_id = info_account.get("channel_id")
    # Nhanh 1: attestationResponseData (UNBOUND)
    c1 = att_get(uploader, "ENGAGEMENT_TYPE_UNBOUND", page_id=page_id)
    snap1 = solve_program(c1)
    # Nhanh 2: CREATOR_STUDIO_ACTION -> att/esr -> reauth -> sessionToken
    ids = [{"externalChannelId": channel_id}] if channel_id else None
    c2 = att_get(uploader, "ENGAGEMENT_TYPE_CREATOR_STUDIO_ACTION", ids=ids, page_id=page_id)
    snap2 = solve_program(c2)
    ivctx = att_esr(uploader, c2["challenge"], snap2, page_id=page_id,
                    info_account=info_account)
    reauth_token, risk_ctx = get_web_reauth_url(
        uploader, ivctx, c2["challenge"], snap2, page_id=page_id,
        info_account=info_account)
    session_token = ars_grst(uploader, risk_ctx, reauth_token, page_id=page_id,
                             info_account=info_account)
    return {"challenge": c1["challenge"], "webResponse": snap1, "ctx": session_token}


def _build_context(info_account: dict, page_id: str, ctx: str = None) -> dict:
    request = {"returnLogEntry": True, "internalExperimentFlags": [],
               "eats": info_account["eats"],
               "consistencyTokenJars": info_account.get("consistency_token_jars", [])}
    if ctx:
        request["sessionInfo"] = {"token": ctx}
    context = {
        "client": {"clientName": 62, "clientVersion": "1.20260709.05.00",
                   "hl": "vi", "gl": "VN", "utcOffsetMinutes": 420,
                   "userInterfaceTheme": "USER_INTERFACE_THEME_LIGHT",
                   "screenWidthPoints": 1111, "screenHeightPoints": 927,
                   "screenPixelDensity": 1, "screenDensityFloat": 1},
        "request": request,
        "user": {},
        "clickTracking": {"visualElement": {"veType": 31402}},
        "clientScreenNonce": "".join(
            random.choices(string.ascii_letters + string.digits + "_-", k=16)),
    }
    if page_id:
        context["user"]["onBehalfOfUser"] = page_id
    if info_account.get("serialized_delegation_context"):
        context["user"]["serializedDelegationContext"] = \
            info_account["serialized_delegation_context"]
    if info_account.get("channel_id"):
        context["user"]["delegationContext"] = {
            "externalChannelId": info_account["channel_id"],
            "roleType": {"channelRoleType": "CREATOR_CHANNEL_ROLE_TYPE_OWNER"},
        }
    return context


# videoReadMask toi thieu de response tra ve trang thai kiem chung
_READ_MASK = {
    "videoId": True, "privacy": True, "timePublishedSeconds": True,
    "draftStatus": True, "status": True,
    "scheduledPublishingDetails": {"all": True},
}


def schedule_publish(uploader, video_id: str, publish_at: int, *,
                     page_id: str, info_account: dict,
                     attestation: dict, privacy: str = "PUBLIC",
                     remove_draft: bool = True) -> dict:
    """Dat lich cong khai that su tren YouTube (metadata_update).

    Payload dung theo request that cua Studio web (HAR): privacyState +
    scheduledPublishing.set + flowType + madeForKids + attestationResponseData
    (challenge + webResponse tu BotGuard) + context.request.sessionInfo.token.

    attestation = dict tu solve_attestation() (ctx/challenge/webResponse).
    """
    ctx = attestation.get("ctx")
    body = {
        "encryptedVideoId": video_id,
        "videoReadMask": _READ_MASK,
        "flowType": "MDE_FLOW_TYPE_UPLOAD",
        "privacyState": {"newPrivacy": "PRIVATE"},
        "scheduledPublishing": {
            "set": {"timeSec": str(int(publish_at)), "privacy": privacy.upper()}
        },
        "madeForKids": {
            "operation": "MDE_MADE_FOR_KIDS_UPDATE_OPERATION_SET",
            "newMfk": "MDE_MADE_FOR_KIDS_TYPE_NOT_MFK",
        },
        "context": _build_context(info_account, page_id, ctx),
        "attestationResponseData": {
            "challenge": attestation.get("challenge", ""),
            "webResponse": attestation.get("webResponse", ""),
        },
    }
    if remove_draft:
        body["draftState"] = {
            "operation": "MDE_DRAFT_STATE_UPDATE_OPERATION_REMOVE_DRAFT_STATE"
        }
    headers = {
        "Accept": "*/*",
        "Authorization": f"SAPISIDHASH {_studio_sapisidhash(uploader)}",
        "Content-Type": "application/json",
        "Origin": YT_STUDIO,
        "User-Agent": USER_AGENT,
        "X-Goog-Authuser": "0",
    }
    if page_id:
        headers["X-Goog-PageId"] = page_id
    res = uploader.session.post(
        f"{YT_STUDIO}/youtubei/v1/video_manager/metadata_update?alt=json",
        headers=headers, data=json.dumps(body), timeout=60,
    )
    uploader.save_cookies()
    if res.status_code != 200:
        raise UploadError(
            f"Dat lich that bai (HTTP {res.status_code}): {res.text[:300]}")
    return res.json()


def read_video_state(uploader, video_id: str, page_id: str = None,
                     info_account: dict = None) -> dict:
    """Doc lai privacy + timePublishedSeconds de verify lich.
    Voi brand channel can delegation day du (info_account) moi tra ket qua."""
    context = {"client": {"clientName": 62, "clientVersion": "1.20260709.05.00",
                          "hl": "en", "gl": "US"}}
    if page_id:
        user = {"onBehalfOfUser": page_id}
        if info_account:
            if info_account.get("serialized_delegation_context"):
                user["serializedDelegationContext"] = \
                    info_account["serialized_delegation_context"]
            if info_account.get("channel_id"):
                user["delegationContext"] = {
                    "externalChannelId": info_account["channel_id"],
                    "roleType": {"channelRoleType": "CREATOR_CHANNEL_ROLE_TYPE_OWNER"},
                }
        context["user"] = user
    headers = {
        "Accept": "*/*",
        "Authorization": f"SAPISIDHASH {_studio_sapisidhash(uploader)}",
        "Content-Type": "application/json", "Origin": YT_STUDIO,
        "User-Agent": USER_AGENT, "X-Goog-Authuser": "0",
    }
    if page_id:
        headers["X-Goog-PageId"] = page_id
    body = {"context": context, "videoIds": [video_id],
            "mask": {"videoId": True, "privacy": True, "timePublishedSeconds": True}}
    res = uploader.session.post(
        f"{YT_STUDIO}/youtubei/v1/creator/get_creator_videos?alt=json",
        headers=headers, data=json.dumps(body), timeout=60,
    )
    videos = res.json().get("videos") or []
    return videos[0] if videos else {}


def schedule_video(uploader, video_id: str, publish_at: int, *,
                   page_id: str = None, privacy: str = "PUBLIC",
                   info_account: dict = None, attestation: dict = None,
                   log=print) -> dict:
    """Tien ich 1-phat: scrape info -> solve attestation -> dat lich.

    Co the truyen san info_account/attestation de tai su dung cho nhieu video.
    """
    if info_account is None:
        log("[Lịch gốc] Lấy thông tin tài khoản (eats)...")
        info_account = scrape_account_info(uploader, page_id)
    if attestation is None:
        log("[Lịch gốc] Giải BotGuard qua Node...")
        attestation = solve_attestation(uploader, info_account, page_id=page_id)
    log("[Lịch gốc] Đặt lịch công khai trên YouTube...")
    return schedule_publish(uploader, video_id, publish_at, page_id=page_id,
                            info_account=info_account, attestation=attestation,
                            privacy=privacy)
