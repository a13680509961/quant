# -*- coding: utf-8 -*-
"""一键发布到公网：Cloudflare 临时隧道优先，网络受限时自动切换 localtunnel。

用法：python publish.py
    - 自动启动量化应用（若未运行）
    - 自动下载 cloudflared（GitHub 直连失败时走镜像）
    - 打印公网地址，Ctrl+C 或关闭窗口即断开

注意：临时隧道地址每次启动都会变；本应用无登录验证，
请勿长期挂公网（详见 README 安全提示）。
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(ROOT, "tools")
PORT = 8000
APP_URL = f"http://127.0.0.1:{PORT}"

CF_BIN = os.path.join(TOOLS, "cloudflared.exe")
CF_URLS = [
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    "https://gh-proxy.com/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
]


def log(msg: str):
    print(msg, flush=True)


def app_running() -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=1.5)
        s.close()
        return True
    except OSError:
        return False


def ensure_app() -> None:
    if app_running():
        log(f"[OK] 应用已在运行：{APP_URL}")
        return
    log("[启动] 正在启动量化应用…")
    flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "app.py"), "--port", str(PORT), "--no-browser"],
        cwd=ROOT, creationflags=flags,
    )
    for _ in range(40):
        time.sleep(1)
        if app_running():
            log(f"[OK] 应用已启动：{APP_URL}")
            return
    raise RuntimeError("应用启动失败，请先手动运行 python app.py 检查原因")


def download_cloudflared() -> bool:
    if os.path.exists(CF_BIN) and os.path.getsize(CF_BIN) > 1_000_000:
        return True
    os.makedirs(TOOLS, exist_ok=True)
    for url in CF_URLS:
        log(f"[下载] cloudflared …")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            if len(data) < 1_000_000:
                raise ValueError("文件不完整")
            with open(CF_BIN, "wb") as f:
                f.write(data)
            log(f"[OK] cloudflared 下载完成（{len(data) // 1024 // 1024} MB）")
            return True
        except Exception as e:
            log(f"[提示] 下载失败：{type(e).__name__}，尝试下一来源…")
    return False


def _spawn(cmd):
    return subprocess.Popen(
        cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def run_tunnel(cmd, pattern, wait_seconds, banner_hint):
    proc = _spawn(cmd)
    found = threading.Event()
    url_box: list = []

    def reader():
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    log("  | " + line[:100])
                m = re.search(pattern, line)
                if m and not url_box:
                    url_box.append(m.group(0))
                    found.set()
        except Exception:
            pass

    threading.Thread(target=reader, daemon=True).start()
    found.wait(wait_seconds)
    if not url_box:
        proc.terminate()
        return None
    print()
    print("=" * 62)
    print(f"  🎉 公网地址：{url_box[0]}")
    if banner_hint:
        print(f"  {banner_hint}")
    print("  按 Ctrl+C（或关闭窗口）即断开")
    print("=" * 62)
    print()
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
    return url_box[0]


def main() -> None:
    print("=" * 62)
    print("  量化应用 · 一键发布到公网")
    print("=" * 62)
    ensure_app()

    # 方式 1：Cloudflare 临时隧道（免费、无需注册）
    if download_cloudflared():
        log("[隧道] 启动 Cloudflare 临时隧道…")
        url = run_tunnel(
            [CF_BIN, "tunnel", "--url", APP_URL, "--no-autoupdate"],
            r"https://[a-z0-9-]+\.trycloudflare\.com",
            45,
            None,
        )
        if url:
            return
        log("[提示] Cloudflare 隧道不可用（当前网络受限），改用 tunnelmole…")

    # 方式 2：tunnelmole（HTTP 隧道，无需注册、无密码页；需本机 Node.js/npx）
    log("[隧道] 启动 tunnelmole…")
    try:
        url = run_tunnel(
            ["npx", "-y", "tunnelmole", str(PORT)],
            r"https://[a-z0-9-]+\.tunnelmole\.net",
            90,
            None,
        )
        if url:
            return
        log("[失败] tunnelmole 未取得地址，改用 localtunnel…")
    except FileNotFoundError:
        log("[提示] 未找到 npx，跳过 tunnelmole（可安装 Node.js https://nodejs.org）")
    except Exception as e:
        log(f"[失败] {type(e).__name__}: {e}")

    # 方式 3：localtunnel（需本机 Node.js/npx；有密码页）
    log("[隧道] 启动 localtunnel…")
    try:
        url = run_tunnel(
            ["npx", "-y", "localtunnel", "--port", str(PORT)],
            r"https://[a-z0-9-]+\.loca\.lt",
            90,
            "首次用浏览器打开如出现密码页，输入页面上显示的服务器 IP 即可",
        )
        if url:
            return
        log("[失败] localtunnel 未取得地址（可能需本机安装 Node.js）")
    except FileNotFoundError:
        log("[失败] 未找到 npx。请安装 Node.js（https://nodejs.org），或参考 README 的其他发布方式")
    except Exception as e:
        log(f"[失败] {type(e).__name__}: {e}")

    # 方式 4：localhost.run（SSH 隧道，Windows 10+ 自带 ssh，无需注册、无密码页）
    log("[隧道] 尝试 SSH 隧道 localhost.run…")
    try:
        url = run_tunnel(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30",
             "-R", f"80:127.0.0.1:{PORT}", "nokey@localhost.run"],
            r"https://[a-z0-9-]+\.lhr\.life",
            45,
            None,
        )
        if url:
            return
        log("[失败] localhost.run 未取得地址（网络可能屏蔽 22 端口）")
    except FileNotFoundError:
        log("[失败] 未找到 ssh。Windows 10+ 可在“设置-应用-可选功能”中添加 OpenSSH 客户端")
    except Exception as e:
        log(f"[失败] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
