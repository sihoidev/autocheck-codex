from __future__ import annotations

from html import escape

import requests

from common import DEFAULT_TIMEOUT, CheckinResult


def telegram_api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def env_value(env: dict[str, str], *names: str) -> str:
    for name in names:
        value = env.get(name, "").strip()
        if value:
            return value
    return ""


def status_text(result: CheckinResult) -> str:
    if result.skipped:
        return "已跳过"
    return "成功" if result.ok else "失败"


def telegram_message(result: CheckinResult) -> str:
    lines = [
        f"<b>{escape(result.name)} 签到通知</b>",
        f"状态: {escape(status_text(result))}",
        f"结果: {escape(result.message)}",
    ]
    if result.details:
        lines.append("")
        lines.extend(escape(detail) for detail in result.details)
    return "\n".join(lines)


def send_telegram_notification(result: CheckinResult, env: dict[str, str]) -> bool:
    token = env_value(env, "TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
    chat_id = env_value(env, "TG_CHAT_ID", "TELEGRAM_CHAT_ID")
    channel_id = env_value(env, "TG_CHANNEL_ID", "TELEGRAM_CHANNEL_ID")
    target_chat_id = channel_id or chat_id

    if not token or not target_chat_id:
        print("[SKIP] telegram: missing TG_BOT_TOKEN and TG_CHANNEL_ID/TG_CHAT_ID")
        return True

    try:
        sent = requests.post(
            telegram_api_url(token, "sendMessage"),
            json={
                "chat_id": target_chat_id,
                "text": telegram_message(result),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=DEFAULT_TIMEOUT,
        )
        sent.raise_for_status()
        payload = sent.json()
        if not payload.get("ok"):
            print(f"[FAIL] telegram {result.name}: sendMessage failed: {payload}")
            return False

        print(f"[OK] telegram {result.name}: message sent")
        return True
    except Exception as exc:
        print(f"[FAIL] telegram {result.name}: request failed: {exc}")
        return False
