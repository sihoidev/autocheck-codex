from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from html import escape
from typing import Any

import requests


DEFAULT_TIMEOUT = 20
BILIBILI_SIGN_OFFLINE_CODES = {1}
BILIBILI_ALREADY_DONE_CODES = {-500, 1011040}
BILIBILI_ALREADY_DONE_TEXT = (
    "already",
    "already signed",
    "今日已",
    "已经",
    "已投",
    "已分享",
    "已观看",
    "已签到",
    "重复",
)


@dataclass
class CheckinResult:
    name: str
    ok: bool
    message: str
    skipped: bool = False


def cookie_headers(cookie: str, referer: str | None = None) -> dict[str, str]:
    headers = {
        "cookie": cookie,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "accept": "application/json, text/plain, */*",
    }
    if referer:
        headers["referer"] = referer
    return headers


def bilibili_csrf(cookie: str) -> str:
    for item in cookie.split(";"):
        key, _, value = item.strip().partition("=")
        if key == "bili_jct":
            return value
    return ""


def bilibili_message(data: dict[str, Any]) -> str:
    message = data.get("message") or data.get("msg")
    if message:
        return str(message)
    payload = data.get("data")
    if isinstance(payload, dict):
        return str(payload.get("text") or payload.get("message") or payload)
    return str(data)


def bilibili_is_already_done(data: dict[str, Any]) -> bool:
    code = data.get("code")
    message = bilibili_message(data).lower()
    return code in BILIBILI_ALREADY_DONE_CODES or any(
        text in message for text in BILIBILI_ALREADY_DONE_TEXT
    )


class BilibiliTask:
    def __init__(self, cookie: str) -> None:
        self.csrf = bilibili_csrf(cookie)
        self.session = requests.Session()
        self.session.headers.update(cookie_headers(cookie, "https://www.bilibili.com/"))

    def get_json(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.session.request(
            method,
            url,
            data=data,
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"unexpected response: {payload!r}")
        return payload

    def login_name(self) -> str | None:
        data = self.get_json("GET", "https://api.bilibili.com/x/web-interface/nav")
        if data.get("code") == 0 and data.get("data", {}).get("isLogin"):
            return str(data.get("data", {}).get("uname") or "logged in")
        return None

    def get_dynamic_videos(self) -> list[str]:
        data = self.get_json(
            "GET",
            "https://api.bilibili.com/x/web-interface/dynamic/region?ps=10&rid=1",
        )
        if data.get("code") != 0:
            return []
        archives = data.get("data", {}).get("archives", [])
        return [str(video["bvid"]) for video in archives if video.get("bvid")]

    def get_ranking_videos(self) -> list[str]:
        data = self.get_json(
            "GET",
            "https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all",
        )
        if data.get("code") != 0:
            return []
        videos = data.get("data", {}).get("list", [])
        return [str(video["bvid"]) for video in videos if video.get("bvid")]

    def candidate_videos(self) -> list[str]:
        videos: list[str] = []
        for bvid in self.get_dynamic_videos() + self.get_ranking_videos():
            if bvid not in videos:
                videos.append(bvid)
        return videos

    def coin_status(self, bvid: str) -> bool:
        data = self.get_json(
            "GET",
            f"https://api.bilibili.com/x/web-interface/archive/coins?bvid={bvid}",
        )
        return data.get("code") == 0 and int(data.get("data", {}).get("multiply") or 0) > 0

    def add_coin(self, bvid: str) -> tuple[bool, str]:
        if not self.csrf:
            return False, "missing bili_jct csrf"
        data = self.get_json(
            "POST",
            "https://api.bilibili.com/x/web-interface/coin/add",
            data={
                "bvid": bvid,
                "multiply": 1,
                "select_like": 1,
                "csrf": self.csrf,
            },
        )
        if data.get("code") == 0:
            return True, f"投币成功: {bvid}"
        if bilibili_is_already_done(data):
            return True, f"投币已完成: {bvid}"
        return False, f"投币失败: {bilibili_message(data)}"

    def share_video(self, bvid: str) -> tuple[bool, str]:
        if not self.csrf:
            return False, "missing bili_jct csrf"
        data = self.get_json(
            "POST",
            "https://api.bilibili.com/x/web-interface/share/add",
            data={"bvid": bvid, "csrf": self.csrf},
        )
        if data.get("code") == 0:
            return True, f"分享成功: {bvid}"
        if bilibili_is_already_done(data):
            return True, f"分享已完成: {bvid}"
        return False, f"分享失败: {bilibili_message(data)}"

    def watch_video(self, bvid: str) -> tuple[bool, str]:
        if not self.csrf:
            return False, "missing bili_jct csrf"
        data = self.get_json(
            "POST",
            "https://api.bilibili.com/x/click-interface/web/heartbeat",
            data={"bvid": bvid, "played_time": 30, "csrf": self.csrf},
        )
        if data.get("code") == 0:
            return True, f"观看成功: {bvid}"
        if bilibili_is_already_done(data):
            return True, f"观看已完成: {bvid}"
        return False, f"观看失败: {bilibili_message(data)}"

    def live_sign(self) -> tuple[bool, str]:
        data = self.get_json(
            "GET",
            "https://api.live.bilibili.com/xlive/web-ucenter/v1/sign/DoSign",
        )
        code = data.get("code")
        message = bilibili_message(data)
        if code == 0:
            return True, f"直播签到成功: {message}"
        if bilibili_is_already_done(data):
            return True, f"直播签到已完成: {message}"
        if code in BILIBILI_SIGN_OFFLINE_CODES:
            return True, f"直播签到已跳过: {message}"
        return False, f"直播签到失败: {message}"

    def manga_sign(self) -> tuple[bool, str]:
        data = self.get_json(
            "POST",
            "https://manga.bilibili.com/twirp/activity.v1.Activity/ClockIn",
            data={"platform": "ios"},
        )
        if data.get("code") == 0:
            return True, "漫画签到成功"
        if bilibili_is_already_done(data):
            return True, f"漫画签到已完成: {bilibili_message(data)}"
        return False, f"漫画签到失败: {bilibili_message(data)}"


def check_bilibili(cookie: str) -> CheckinResult:
    if not cookie:
        return CheckinResult("Bilibili", False, "missing BILIBILI_COOKIE secret")

    task = BilibiliTask(cookie)
    steps: list[tuple[bool, str]] = []

    try:
        login_name = task.login_name()
        if not login_name:
            return CheckinResult("Bilibili", False, "login check failed")

        steps.append((True, f"登录正常: {login_name}"))

        videos = task.candidate_videos()
        if not videos:
            steps.append((False, "未找到可用于观看/分享/投币的视频"))
        else:
            selected = videos[0]
            steps.append(task.watch_video(selected))
            steps.append(task.share_video(selected))

            coin_video = ""
            for bvid in videos:
                if not task.coin_status(bvid):
                    coin_video = bvid
                    break
            if coin_video:
                steps.append(task.add_coin(coin_video))
            else:
                steps.append((True, "投币已完成: 候选视频都已投过币"))

        steps.append(task.live_sign())
        steps.append(task.manga_sign())
    except Exception as exc:
        return CheckinResult("Bilibili", False, f"request failed: {exc}")

    ok = all(step_ok for step_ok, _ in steps)
    message = "；".join(step_message for _, step_message in steps)
    return CheckinResult("Bilibili", ok, message)


def check_v2ex(cookie: str) -> CheckinResult:
    if not cookie:
        return CheckinResult("V2EX", False, "missing V2EX_COOKIE secret")

    session = requests.Session()
    session.headers.update(cookie_headers(cookie, "https://www.v2ex.com/mission/daily"))

    try:
        page = session.get(
            "https://www.v2ex.com/mission/daily",
            timeout=DEFAULT_TIMEOUT,
        )
        page.raise_for_status()
        html = page.text

        if "/signin" in page.url or "signout" not in html:
            return CheckinResult("V2EX", False, "login check failed")

        match = re.search(r"/mission/daily/redeem\?once=(\d+)", html)
        if not match:
            return CheckinResult("V2EX", True, "already checked in")

        redeem = session.get(
            f"https://www.v2ex.com/mission/daily/redeem?once={match.group(1)}",
            timeout=DEFAULT_TIMEOUT,
        )
        redeem.raise_for_status()

        verify = session.get(
            "https://www.v2ex.com/mission/daily",
            timeout=DEFAULT_TIMEOUT,
        )
        verify.raise_for_status()
        if not re.search(r"/mission/daily/redeem\?once=(\d+)", verify.text):
            return CheckinResult("V2EX", True, "checked in")
    except Exception as exc:
        return CheckinResult("V2EX", False, f"request failed: {exc}")

    return CheckinResult("V2EX", False, "check-in result could not be verified")


def telegram_api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def checkin_status_text(result: CheckinResult) -> str:
    return "成功打卡" if result.ok else "打卡失败"


def send_telegram_notification(results: list[CheckinResult]) -> bool:
    token = env_value("TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
    chat_id = env_value("TG_CHAT_ID", "TELEGRAM_CHAT_ID")
    channel_id = env_value("TG_CHANNEL_ID", "TELEGRAM_CHANNEL_ID")
    target_chat_id = channel_id or chat_id

    if not token or not target_chat_id:
        print("[SKIP] telegram: missing TG_BOT_TOKEN and TG_CHANNEL_ID/TG_CHAT_ID")
        return True

    title = "自动打卡通知"
    lines = [f"<b>{escape(title)}</b>", ""]
    for result in results:
        status_text = checkin_status_text(result)
        lines.append(f"<b>{escape(result.name)}</b>：{escape(status_text)}")
        lines.append(f"原因：{escape(result.message)}")
        lines.append("")

    message = "\n".join(lines)
    try:
        sent = requests.post(
            telegram_api_url(token, "sendMessage"),
            json={
                "chat_id": target_chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        sent.raise_for_status()
        payload = sent.json()
        if not payload.get("ok"):
            print(f"[FAIL] telegram: sendMessage failed: {payload}")
            return False

        print("[OK] telegram: message sent")
        return True
    except Exception as exc:
        print(f"[FAIL] telegram: request failed: {exc}")
        return False


def main() -> int:
    checks = [
        check_bilibili(os.getenv("BILIBILI_COOKIE", "").strip()),
        check_v2ex(os.getenv("V2EX_COOKIE", "").strip()),
    ]

    failed = False
    for result in checks:
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: {result.message}")
        failed = failed or not result.ok

    notification_ok = send_telegram_notification(checks)

    return 1 if failed or not notification_ok else 0


if __name__ == "__main__":
    sys.exit(main())
