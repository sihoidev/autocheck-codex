from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_TIMEOUT = 20


@dataclass
class CheckinResult:
    name: str
    ok: bool
    message: str
    details: list[str] = field(default_factory=list)
    skipped: bool = False

    def text(self) -> str:
        if not self.details:
            return self.message
        return "\n".join([self.message, *self.details])


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
