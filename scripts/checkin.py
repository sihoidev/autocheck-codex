from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass

import requests


DEFAULT_TIMEOUT = 20


@dataclass
class CheckinResult:
    name: str
    ok: bool
    message: str


def cookie_headers(cookie: str, referer: str | None = None) -> dict[str, str]:
    headers = {
        "cookie": cookie,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if referer:
        headers["referer"] = referer
    return headers


def check_bilibili(cookie: str) -> CheckinResult:
    if not cookie:
        return CheckinResult("bilibili", False, "missing BILIBILI_COOKIE secret")

    session = requests.Session()
    session.headers.update(cookie_headers(cookie, "https://live.bilibili.com/"))

    try:
        nav = session.get(
            "https://api.bilibili.com/x/web-interface/nav",
            timeout=DEFAULT_TIMEOUT,
        )
        nav.raise_for_status()
        nav_data = nav.json()
        if nav_data.get("code") != 0 or not nav_data.get("data", {}).get("isLogin"):
            return CheckinResult("bilibili", False, f"login check failed: {nav_data}")

        response = session.get(
            "https://api.live.bilibili.com/xlive/web-ucenter/v1/sign/DoSign",
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return CheckinResult("bilibili", False, f"request failed: {exc}")

    code = data.get("code")
    message = data.get("message") or data.get("msg") or str(data)
    if code == 0:
        return CheckinResult("bilibili", True, message)
    if code in {-500, 1011040} or "already" in message.lower():
        return CheckinResult("bilibili", True, message)
    return CheckinResult("bilibili", False, f"check-in failed: {data}")


def check_v2ex(cookie: str) -> CheckinResult:
    if not cookie:
        return CheckinResult("v2ex", False, "missing V2EX_COOKIE secret")

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
            return CheckinResult("v2ex", False, "login check failed")

        match = re.search(r"/mission/daily/redeem\?once=(\d+)", html)
        if not match:
            return CheckinResult("v2ex", True, "already checked in")

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
            return CheckinResult("v2ex", True, "checked in")
    except Exception as exc:
        return CheckinResult("v2ex", False, f"request failed: {exc}")

    return CheckinResult("v2ex", False, "check-in result could not be verified")


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

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
