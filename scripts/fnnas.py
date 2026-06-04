from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin

import requests

from common import DEFAULT_TIMEOUT, CheckinResult, cookie_headers


FNNAS_BASE_URL = "https://club.fnnas.com/"
FNNAS_SIGN_URL = urljoin(FNNAS_BASE_URL, "plugin.php?id=zqlj_sign")


def strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def response_text(response: requests.Response) -> str:
    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "ascii"}:
        response.encoding = response.apparent_encoding
    return response.text


def cookie_value(cookie: str, name: str) -> str:
    match = re.search(rf"(?:^|;\s*){re.escape(name)}=([^;]+)", cookie)
    return unescape(match.group(1)) if match else ""


def parse_sign_data(value: str) -> tuple[str, str, str]:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    data: dict[str, str] = {}
    plain: list[str] = []

    for line in lines:
        if "=" not in line:
            plain.append(line)
            continue

        key, item = line.split("=", 1)
        data[key.strip()] = item.strip()

    saltkey = data.get("fn_pvRK_2132_saltkey") or data.get("pvRK_2132_saltkey")
    auth = data.get("fn_pvRK_2132_auth") or data.get("pvRK_2132_auth")
    sign = data.get("fn_pvRK_2132_sign") or data.get("pvRK_2132_sign")

    if not (saltkey and auth and sign) and len(plain) >= 3:
        saltkey, auth, sign = plain[:3]

    return saltkey or "", auth or "", sign or ""


def parse_sign_button(html: str) -> tuple[str | None, str | None]:
    button_match = re.search(
        r"""<[^>]*class=["'][^"']*\bsignbtn\b[^"']*["'][^>]*>.*?<a\b([^>]*)>(.*?)</a>""",
        html,
        flags=re.S | re.I,
    )
    if not button_match:
        button_match = re.search(
            r"""<a\b([^>]*)class=["'][^"']*\bbtna\b[^"']*["'][^>]*>(.*?)</a>""",
            html,
            flags=re.S | re.I,
        )

    if not button_match:
        return None, None

    attrs, label_html = button_match.groups()
    text = strip_tags(label_html)
    href_match = re.search(r"""href=["']([^"']+)["']""", attrs, flags=re.I)
    href = unescape(href_match.group(1)) if href_match else ""
    sign_match = re.search(r"[?&]sign=([^&\"']+)", href)
    return text, sign_match.group(1) if sign_match else None


def parse_sign_info(html: str) -> list[str]:
    text = strip_tags(html)
    details: list[str] = []
    patterns = [
        r"最近打卡时间[:：]\s*[^ ]+",
        r"本月打卡天数[:：]\s*\d+\s*天?",
        r"连续打卡天数[:：]\s*\d+\s*天?",
        r"累计打卡天数[:：]\s*\d+\s*天?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            details.append(match.group(0))

    return details


def page_looks_logged_out(html: str, final_url: str) -> bool:
    return (
        "member.php?mod=logging&action=login" in final_url
        or "member.php?mod=logging&action=login" in html
        or "登录" in strip_tags(html) and "退出" not in strip_tags(html)
    )


class FNNASCheckin:
    def __init__(self, cookie: str = "", saltkey: str = "", auth: str = "") -> None:
        self.session = requests.Session()
        self.session.headers.update(cookie_headers(cookie, FNNAS_SIGN_URL))
        self.session.headers.update(
            {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
        )
        if saltkey:
            self.session.cookies.set("pvRK_2132_saltkey", saltkey, domain="club.fnnas.com")
        if auth:
            self.session.cookies.set("pvRK_2132_auth", auth, domain="club.fnnas.com")

    def sign_page(self) -> tuple[str, str]:
        response = self.session.get(FNNAS_SIGN_URL, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response_text(response), response.url

    def do_sign(self, sign_param: str) -> str:
        response = self.session.get(
            f"{FNNAS_SIGN_URL}&sign={sign_param}",
            headers={"referer": FNNAS_SIGN_URL},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        return response_text(response)


def response_means_signed(html: str) -> bool:
    text = strip_tags(html)
    return (
        "打卡成功" in text
        or "签到成功" in text
        or "已经打过卡" in text
        or "已经签到" in text
        or "今日已打卡" in text
    )


def check_fnnas(
    cookie: str = "",
    saltkey: str = "",
    auth: str = "",
    sign: str = "",
    sign_data: str = "",
) -> CheckinResult:
    data_saltkey, data_auth, data_sign = parse_sign_data(sign_data)
    saltkey = saltkey or data_saltkey
    auth = auth or data_auth
    sign = sign or data_sign
    saltkey = saltkey or cookie_value(cookie, "pvRK_2132_saltkey")
    auth = auth or cookie_value(cookie, "pvRK_2132_auth")

    if sign and saltkey and auth:
        return check_fnnas_direct(saltkey, auth, sign)

    if not cookie:
        return CheckinResult(
            "飞牛社区",
            False,
            "missing FNNAS_COOKIE secret or fn_pvRK_2132_saltkey/fn_pvRK_2132_auth/fn_pvRK_2132_sign secrets",
        )

    task = FNNASCheckin(cookie)
    details: list[str] = []

    try:
        html, page_url = task.sign_page()
        if page_looks_logged_out(html, page_url):
            return CheckinResult("飞牛社区", False, "login check failed")

        sign_text, sign_param = parse_sign_button(html)
        if sign_text:
            details.append(f"当前状态: {sign_text}")
        details.extend(parse_sign_info(html))

        if sign_text and "已" in sign_text and ("打卡" in sign_text or "签到" in sign_text):
            return CheckinResult("飞牛社区", True, "今日已签到", details=details)

        if not sign_param:
            return CheckinResult("飞牛社区", False, "未找到签到按钮或 sign 参数", details=details)

        task.do_sign(sign_param)
        verify_html, verify_url = task.sign_page()
        if page_looks_logged_out(verify_html, verify_url):
            return CheckinResult("飞牛社区", False, "签到后登录状态失效", details=details)

        verify_text, _ = parse_sign_button(verify_html)
        verify_details = parse_sign_info(verify_html)
        if verify_text:
            details.append(f"签到后状态: {verify_text}")
        details.extend(item for item in verify_details if item not in details)

        if verify_text and "已" in verify_text and ("打卡" in verify_text or "签到" in verify_text):
            return CheckinResult("飞牛社区", True, "签到成功", details=details)

        return CheckinResult("飞牛社区", False, "签到请求已发送，但未验证到已签到状态", details=details)
    except requests.RequestException as exc:
        return CheckinResult("飞牛社区", False, f"request failed: {exc}", details=details)
    except Exception as exc:
        return CheckinResult("飞牛社区", False, f"check failed: {exc}", details=details)


def check_fnnas_direct(saltkey: str, auth: str, sign: str) -> CheckinResult:
    task = FNNASCheckin(saltkey=saltkey, auth=auth)
    details = ["使用 saltkey/auth/sign 直连签到模式"]

    try:
        sign_html = task.do_sign(sign)
        if response_means_signed(sign_html):
            info_html, _ = task.sign_page()
            details.extend(parse_sign_info(info_html))
            return CheckinResult("飞牛社区", True, "签到成功或今日已签到", details=details)

        text = strip_tags(sign_html)
        if "登录" in text and "退出" not in text:
            return CheckinResult("飞牛社区", False, "登录状态失效，请更新 saltkey/auth/sign", details=details)

        snippet = text[:120] if text else "empty response"
        details.append(f"响应摘要: {snippet}")
        return CheckinResult("飞牛社区", False, "直连签到未返回成功状态", details=details)
    except requests.RequestException as exc:
        return CheckinResult("飞牛社区", False, f"request failed: {exc}", details=details)
    except Exception as exc:
        return CheckinResult("飞牛社区", False, f"check failed: {exc}", details=details)
