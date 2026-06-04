from __future__ import annotations

import os
import sys

from bilibili import check_bilibili
from common import CheckinResult
from fnnas import check_fnnas
from notify import send_telegram_notification
from railgun import RAILGUN_BASE_URL, RAILGUN_DEFAULT_TOKEN, check_railgun
from v2ex import check_v2ex


def print_result(result: CheckinResult) -> None:
    status = "OK" if result.ok else "FAIL"
    print(f"[{status}] {result.name}: {result.message}")
    for detail in result.details:
        print(f"  - {detail}")


def main() -> int:
    env = dict(os.environ)
    checks = [
        check_bilibili(env.get("BILIBILI_COOKIE", "").strip()),
        check_v2ex(env.get("V2EX_COOKIE", "").strip()),
        check_railgun(
            env.get("RAILGUN_COOKIE", "").strip()
            or env.get("GLADOS_COOKIE", "").strip()
            or env.get("GLADOS", "").strip(),
            env.get("RAILGUN_BASE_URL", RAILGUN_BASE_URL).strip() or RAILGUN_BASE_URL,
            env.get("RAILGUN_TOKEN", RAILGUN_DEFAULT_TOKEN).strip() or RAILGUN_DEFAULT_TOKEN,
        ),
        check_fnnas(env.get("FNNAS_COOKIE", "").strip()),
    ]

    failed = False
    notification_failed = False
    for result in checks:
        print_result(result)
        failed = failed or not result.ok
        notification_failed = notification_failed or not send_telegram_notification(
            result,
            env,
        )

    return 1 if failed or notification_failed else 0


if __name__ == "__main__":
    sys.exit(main())
