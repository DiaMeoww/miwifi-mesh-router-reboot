#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

# ==================== 用户配置区 ====================
# 0 = 立刻执行一次；1 = 按计划时间执行。
RUN_MODE = 0

# 路由器管理密码：请把引号里的文字改成你的路由器管理密码。
MIWIFI_PASSWORD = "请在这里填写路由器管理密码"

# 路由器登录网址：请填写路由器登录网址，格式为 http://192.168.x.x。
MIWIFI_HOST = "http://192.168.x.x"
MIWIFI_USERNAME = "admin"
SCHEDULE_WEEKDAY = "monday"
SCHEDULE_HOUR = 4
SCHEDULE_MINUTE = 59

# 默认直连路由器。只有在路由器 API 必须走代理时，才改成 True。
MIWIFI_USE_PROXY = False
# ================== 用户配置区结束 ==================

PASSWORD_PLACEHOLDER = "请在这里填写路由器管理密码"
HOST_PLACEHOLDER = "http://192.168.x.x"
REQUEST_TIMEOUT_SECONDS = 15


URL_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler(None if MIWIFI_USE_PROXY else {})
)


def _force_utf8_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    line = f"[{now_text()}] {message}"
    print(line, flush=True)


def sha1_hex(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def normalize_host(host: str) -> str:
    host = host.strip().rstrip("/")
    if not host:
        raise ValueError("MIWIFI_HOST cannot be empty.")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


def request_json(url: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    encoded_data = None
    if data is not None:
        encoded_data = urllib.parse.urlencode(data).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=encoded_data,
        headers={
            "User-Agent": "miwifi-weekly-reboot/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
        method="POST" if encoded_data is not None else "GET",
    )

    try:
        with URL_OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Router returned non-JSON response: {body[:300]}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(f"Router returned unexpected JSON: {parsed!r}")
    return parsed


def request_text(url: str) -> str:
    request = urllib.request.Request(
        url=url,
        headers={"User-Agent": "miwifi-weekly-reboot/1.0"},
        method="GET",
    )
    try:
        with URL_OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


@dataclass(frozen=True)
class LoginSecrets:
    device_id: str
    key: str


@dataclass(frozen=True)
class RouterConfig:
    host: str
    username: str
    password: str


def extract_login_secrets(login_html: str) -> LoginSecrets:
    key_match = re.search(r"key:\s*'([^']+)'", login_html)
    device_match = re.search(r"var\s+deviceId\s*=\s*'([^']+)'", login_html)

    if not key_match:
        raise RuntimeError("Cannot find login key in router login page.")
    if not device_match:
        raise RuntimeError("Cannot find deviceId in router login page.")

    return LoginSecrets(device_id=device_match.group(1), key=key_match.group(1))


def build_nonce(device_id: str) -> str:
    timestamp = int(time.time())
    random_part = random.randint(0, 9999)
    return f"0_{device_id}_{timestamp}_{random_part}"


def encrypt_password(password: str, nonce: str, key: str) -> str:
    password_hash = sha1_hex(password + key)
    return sha1_hex(nonce + password_hash)


def login(config: RouterConfig) -> str:
    login_page = request_text(f"{config.host}/cgi-bin/luci/web")
    secrets = extract_login_secrets(login_page)
    nonce = build_nonce(secrets.device_id)
    encrypted_password = encrypt_password(config.password, nonce, secrets.key)

    rsp = request_json(
        f"{config.host}/cgi-bin/luci/api/xqsystem/login",
        {
            "username": config.username,
            "password": encrypted_password,
            "logtype": 2,
            "nonce": nonce,
        },
    )

    if rsp.get("code") != 0:
        message = rsp.get("msg") or rsp
        raise RuntimeError(f"Login failed: {message}")

    token = rsp.get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"Login succeeded but token is missing: {rsp}")

    return token


def reboot(config: RouterConfig) -> dict[str, Any]:
    token = login(config)
    reboot_url = f"{config.host}/cgi-bin/luci/;stok={urllib.parse.quote(token)}/api/xqsystem/reboot"
    rsp = request_json(reboot_url + "?client=web")

    if rsp.get("code") != 0:
        message = rsp.get("msg") or rsp
        raise RuntimeError(f"Reboot failed: {message}")

    return rsp


def test_login(config: RouterConfig) -> None:
    token = login(config)
    log(f"登录成功，已取得 token 前 6 位：{token[:6]}***；未执行重启。")


def read_config(args: argparse.Namespace) -> RouterConfig:
    host = normalize_host(args.host or MIWIFI_HOST)
    username = args.username or MIWIFI_USERNAME
    password = args.password or MIWIFI_PASSWORD

    if host == HOST_PLACEHOLDER:
        raise RuntimeError(
            "缺少路由器登录网址。请先打开脚本，"
            "把用户配置区里的 MIWIFI_HOST 改成你的路由器登录网址，格式为 http://192.168.x.x。"
        )

    if not password or password == PASSWORD_PLACEHOLDER:
        raise RuntimeError(
            "缺少路由器管理密码。请先打开脚本，"
            "把用户配置区里的 MIWIFI_PASSWORD 改成你的路由器管理密码。"
        )

    return RouterConfig(host=host, username=username, password=password)


def next_run_time(weekday: int, hour: int, minute: int) -> dt.datetime:
    now = dt.datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - now.weekday()) % 7
    if days_ahead == 0 and target <= now:
        days_ahead = 7
    return target + dt.timedelta(days=days_ahead)


def daemon_loop(config: RouterConfig, weekday: int, hour: int, minute: int) -> None:
    while True:
        target = next_run_time(weekday, hour, minute)
        log(f"下一次计划重启时间：{target.strftime('%Y-%m-%d %H:%M:%S')}")

        while True:
            seconds = (target - dt.datetime.now()).total_seconds()
            if seconds <= 0:
                break
            time.sleep(min(seconds, 300))

        try:
            rsp = reboot(config)
            log(f"重启命令发送成功：{json.dumps(rsp, ensure_ascii=False)}")
        except Exception as exc:
            log(f"重启失败：{exc}")

        time.sleep(60)


def parse_weekday(value: str) -> int:
    normalized = value.strip().lower()
    if normalized not in WEEKDAYS:
        allowed = ", ".join(WEEKDAYS)
        raise argparse.ArgumentTypeError(f"weekday must be one of: {allowed}")
    return WEEKDAYS[normalized]


def bounded_int(name: str, minimum: int, maximum: int):
    def parser(value: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} must be an integer.") from exc
        if number < minimum or number > maximum:
            raise argparse.ArgumentTypeError(f"{name} must be between {minimum} and {maximum}.")
        return number

    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reboot a MiWiFi/Redmi router by API, weekly by default.",
    )
    parser.add_argument("--host", help=f"Router base URL, default: {MIWIFI_HOST}")
    parser.add_argument("--username", help=f"Router username, default: {MIWIFI_USERNAME}")
    parser.add_argument("--password", help="Router admin password. Prefer the MIWIFI_PASSWORD value in this file.")
    parser.add_argument(
        "--weekday",
        type=parse_weekday,
        default=parse_weekday(SCHEDULE_WEEKDAY),
        help="Run weekday: monday/tuesday/.../sunday. Default: monday.",
    )
    parser.add_argument(
        "--hour",
        type=bounded_int("hour", 0, 23),
        default=SCHEDULE_HOUR,
        help="Run hour, 0-23. Default: 4.",
    )
    parser.add_argument(
        "--minute",
        type=bounded_int("minute", 0, 59),
        default=SCHEDULE_MINUTE,
        help="Run minute, 0-59. Default: 59.",
    )
    parser.add_argument("--test-login", action="store_true", help="Only verify login, do not reboot.")
    return parser


def main() -> int:
    _force_utf8_console()
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = read_config(args)
        if args.test_login:
            test_login(config)
        elif RUN_MODE == 0:
            rsp = reboot(config)
            log(f"重启命令发送成功：{json.dumps(rsp, ensure_ascii=False)}")
        elif RUN_MODE == 1:
            daemon_loop(config, args.weekday, args.hour, args.minute)
        else:
            raise RuntimeError("RUN_MODE 只能设置为 0 或 1。")
        return 0
    except KeyboardInterrupt:
        log("收到 Ctrl+C，脚本已退出。")
        return 130
    except Exception as exc:
        log(f"执行失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
