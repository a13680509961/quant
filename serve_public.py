# -*- coding: utf-8 -*-
"""长期在线模式：服务 + 公网隧道 + 源码变更自动重启（更新直接同步到公网）。

用法：python serve_public.py
    - 启动量化应用（崩溃自动拉起）
    - 启动公网隧道（tunnelmole 优先，失败换 localtunnel；断开自动重建）
    - 每 3 秒检查源码：
        quant/*.py 变更   → 自动重启后端（1~2 秒完成）
        前端文件变更       → 无需重启，所有打开页面的浏览器 20 秒内自动刷新
    - 当前公网地址写入 public_url.txt，终端实时打印
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8000
WATCH_DIRS = ("quant", "web")
LOG = os.path.join(ROOT, "data", "serve_public.log")
URL_FILE = os.path.join(ROOT, "public_url.txt")
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def snapshot() -> dict:
    sig = {}
    for sub in WATCH_DIRS:
        base = os.path.join(ROOT, sub)
        for dirname, _dirs, files in os.walk(base):
            for f in files:
                if f.endswith((".py", ".js", ".css", ".html", ".json")):
                    p = os.path.join(dirname, f)
                    try:
                        sig[p] = os.path.getmtime(p)
                    except OSError:
                        pass
    return sig


def spawn(cmd) -> subprocess.Popen:
    f = open(LOG, "ab")
    return subprocess.Popen(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                            creationflags=FLAGS)


def npx_cmd():
    """返回可用的 npx 启动命令前缀：优先 DSH 内置 node+pnpm dlx，其次系统 npx。"""
    dsh = os.path.expanduser(r"~\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies")
    node = os.path.join(dsh, "node", "bin", "node.exe")
    pnpm = os.path.join(dsh, "pnpm", "bin", "pnpm.mjs")
    if os.path.exists(node) and os.path.exists(pnpm):
        return [node, pnpm, "dlx"]
    if shutil.which("npx"):
        return ["cmd", "/c", "npx", "-y"]  # Windows 的 npx.cmd 需经 cmd 启动
    return None


def free_port(port: int) -> None:
    """确保端口空闲：若被旧进程占用（如前次守护遗留），结束它。"""
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        s.close()
        return
    except OSError:
        pass
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"],
                             capture_output=True, text=True, timeout=15).stdout
        for line in out.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid = int(line.split()[-1])
                log(f"端口 {port} 被进程 {pid} 占用，结束它…")
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True, timeout=15)
                time.sleep(1)
    except Exception:
        pass


def last_url(pattern: str):
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            hits = re.findall(pattern, f.read())
        return hits[-1] if hits else None
    except OSError:
        return None


def start_app():
    log("启动量化应用…")
    return spawn([sys.executable, os.path.join(ROOT, "app.py"),
                  "--port", str(PORT), "--no-browser"])


def start_tunnel(subdomain: str = ""):
    """返回 (proc, url)；npx 首次安装较慢，最多等 3 分钟。

    subdomain 指定固定子域名（https://<名字>.tunnelmole.net，地址长期不变；
    被占用时自动退回随机地址）。
    """
    base = npx_cmd()
    if base is None:
        log("[失败] 未找到 npx/Node.js（tunnelmole/localtunnel 需要），稍后重试")
        return None, None
    tm_cmd = base + ["tunnelmole", str(PORT)]
    tm_pat = r"https://[a-z0-9-]+\.tunnelmole\.net"
    if subdomain:
        tm_cmd += ["as", subdomain]
        tm_pat = rf"https://{re.escape(subdomain)}\.tunnelmole\.net"
    candidates = [
        ("tunnelmole", tm_cmd, tm_pat),
        ("localtunnel", base + ["localtunnel", "--port", str(PORT)],
         r"https://[a-z0-9-]+\.loca\.lt"),
    ]
    for name, cmd, pat in candidates:
        log(f"启动 {name} 隧道…")
        proc = spawn(cmd)
        url = None
        for _ in range(60):
            time.sleep(3)
            url = last_url(pat)
            if url:
                return proc, url
            if proc.poll() is not None:
                break
        try:
            proc.terminate()
        except Exception:
            pass
        log(f"{name} 未取得地址，尝试下一种…")
    return None, None


def save_url(url: str) -> None:
    if not url:
        return
    try:
        with open(URL_FILE, "w", encoding="utf-8") as f:
            f.write(url + "\n")
    except OSError:
        pass


def main() -> None:
    global PORT
    import argparse
    parser = argparse.ArgumentParser(description="长期在线模式：服务 + 公网隧道 + 自动同步")
    parser.add_argument("--subdomain", default="", help="固定子域名（https://<名字>.tunnelmole.net，地址长期不变）")
    parser.add_argument("--port", type=int, default=PORT, help="本地端口（默认 8000）")
    args = parser.parse_args()
    PORT = args.port
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        open(LOG, "w", encoding="utf-8").close()  # 清空旧日志，避免匹配到历史地址
    except OSError:
        pass
    log("=" * 60)
    log("长期在线模式：后端 .py 变更自动重启；前端变更浏览器 20 秒内自动刷新")
    if args.subdomain:
        log(f"固定子域名：https://{args.subdomain}.tunnelmole.net（被占用则自动退回随机地址）")
    log("=" * 60)

    free_port(PORT)   # 接管前次遗留进程
    app_proc = start_app()
    time.sleep(2)
    tunnel_proc, url = start_tunnel(args.subdomain)
    save_url(url)
    if url:
        log(f"🎉 公网地址：{url}")
    else:
        log("[警告] 未取得公网地址（网络受限时稍后自动重试）")

    last_sig = snapshot()
    last_tunnel_retry = time.time()
    while True:
        time.sleep(3)
        # 1) 后端源码变更 → 自动重启（前端文件变更无需重启，浏览器端自动刷新）
        new_sig = snapshot()
        changed = [p for p in new_sig if p not in last_sig or new_sig[p] != last_sig[p]]
        if last_sig and any(p.endswith(".py") for p in changed):
            log(f"检测到后端变更（{len(changed)} 个文件），重启服务…")
            try:
                app_proc.terminate()
                app_proc.wait(timeout=10)
            except Exception:
                app_proc.kill()
            time.sleep(1)
            app_proc = start_app()
        last_sig = new_sig
        # 2) 应用崩溃 → 自动拉起
        if app_proc.poll() is not None:
            log("应用已退出，自动重启…")
            app_proc = start_app()
        # 3) 隧道断开 → 自动重建（限频：至少间隔 60 秒）
        if (tunnel_proc is None or tunnel_proc.poll() is not None) and \
                time.time() - last_tunnel_retry > 60:
            last_tunnel_retry = time.time()
            log("隧道已断开，自动重建…")
            tunnel_proc, url = start_tunnel(args.subdomain)
            save_url(url)
            if url:
                log(f"🎉 新公网地址：{url}")


if __name__ == "__main__":
    main()
