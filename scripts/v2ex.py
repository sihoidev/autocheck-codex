from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape

import requests

from common import DEFAULT_TIMEOUT, CheckinResult, cookie_headers


V2EX_BASE_URL = "https://www.v2ex.com"
V2EX_MISSION_URL = f"{V2EX_BASE_URL}/mission/daily"
V2EX_BALANCE_URL = f"{V2EX_BASE_URL}/balance"


@dataclass
class V2EXBalance:
    reward: str = ""
    total: str = ""
    description: str = ""
    occurred_at: str = ""


def strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def today_yyyymmdd() -> str:
    # V2EX daily mission runs in Beijing time.
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")


def parse_redeem_path(html: str) -> str | None:
    match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", html)
    if match:
        return match.group(1)
    match = re.search(r'href="(/mission/daily/redeem\?once=\d+)"', html)
    if match:
        return match.group(1)
    return None


def parse_streak(html: str) -> str:
    text = strip_tags(html)
    match = re.search(r"已连续登录\s*\d+\s*天", text)
    return match.group(0) if match else ""


def parse_balance(html: str) -> V2EXBalance:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I)
    today = today_yyyymmdd()
    fallback = V2EXBalance()

    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)
        if len(cells) < 5:
            continue

        occurred_at = strip_tags(cells[0])
        amount = strip_tags(cells[2])
        total = strip_tags(cells[3])
        description = strip_tags(cells[4])
        balance = V2EXBalance(
            reward=amount,
            total=total,
            description=description,
            occurred_at=occurred_at,
        )

        if not fallback.total:
            fallback = balance
        if today in description or today in occurred_at.replace("-", ""):
            return balance

    return fallback


class V2EXTask:
    def __init__(self, cookie: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(cookie_headers(cookie, V2EX_MISSION_URL))

    def get_text(self, url: str, *, referer: str | None = None) -> str:
        headers = {"referer": referer} if referer else None
        response = self.session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.text

    def mission_page(self) -> tuple[str, str]:
        response = self.session.get(V2EX_MISSION_URL, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.text, response.url

    def redeem(self, path: str) -> None:
        url = path if path.startswith("https://") else f"{V2EX_BASE_URL}{path}"
        response = self.session.get(
            url,
            headers={"referer": V2EX_MISSION_URL},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()

    def balance(self) -> V2EXBalance:
        return parse_balance(self.get_text(V2EX_BALANCE_URL, referer=V2EX_MISSION_URL))


def check_v2ex(cookie: str) -> CheckinResult:
    if not cookie:
        return CheckinResult("V2EX", False, "missing V2EX_COOKIE secret")

    task = V2EXTask(cookie)
    details: list[str] = []

    try:
        html, page_url = task.mission_page()
        if "/signin" in page_url or "signout" not in html:
            return CheckinResult("V2EX", False, "login check failed")

        streak = parse_streak(html)
        if streak:
            details.append(f"连续登录: {streak}")

        redeem_path = parse_redeem_path(html)
        if redeem_path == "/balance":
            mission_status = "今日已领取"
        elif redeem_path:
            task.redeem(redeem_path)
            mission_status = "领取成功"
        else:
            return CheckinResult("V2EX", False, "未找到领取按钮或余额入口")

        balance = task.balance()
    except Exception as exc:
        return CheckinResult("V2EX", False, f"request failed: {exc}", details=details)

    details.insert(0, f"任务状态: {mission_status}")
    if balance.reward:
        details.append(f"今日/最近奖励: {balance.reward} 铜币")
    if balance.total:
        details.append(f"当前余额: {balance.total} 铜币")
    if balance.description:
        details.append(f"余额记录: {balance.description}")
    if balance.occurred_at:
        details.append(f"记录时间: {balance.occurred_at}")

    return CheckinResult("V2EX", True, mission_status, details=details)
