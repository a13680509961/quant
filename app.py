# -*- coding: utf-8 -*-
"""量化应用 Web 服务入口（纯 Python 标准库，零第三方 Web 依赖）。

启动：python app.py            （默认 127.0.0.1:8000，自动打开浏览器）
自测：python app.py --selftest （不启动服务，只跑引擎自检）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import urllib.parse
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 允许从项目根目录直接运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quant.backtest import last_signal, run_backtest      # noqa: E402
from quant.data.base import ensure_registered, list_sources  # noqa: E402
from quant.storage import MarketData                      # noqa: E402
from quant.strategies import get_strategy, list_strategies  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")

market = MarketData()
ensure_registered()


# ---------------------------------------------------------------------------
# API 实现
# ---------------------------------------------------------------------------
def api_sources(_query, _body):
    return list_sources()


def api_strategies(_query, _body):
    return list_strategies()


def api_backtest(_query, body):
    source = (body or {}).get("source", "synthetic")
    symbol = (body or {}).get("symbol", "")
    interval = (body or {}).get("interval", "1d")
    strategy_name = (body or {}).get("strategy", "ma_cross")
    params = (body or {}).get("params") or {}
    initial_capital = float((body or {}).get("initial_capital", 100_000))
    fee_rate = float((body or {}).get("fee_rate", 0.0003))
    limit = int((body or {}).get("limit", 500))
    leverage = float((body or {}).get("leverage", 1.0) or 1.0)
    direction = ((body or {}).get("direction") or "").strip() or \
        ("both" if (body or {}).get("allow_short") else "long")  # 兼容旧参数
    if direction not in ("long", "short", "both"):
        raise ValueError(f"未知交易方向：{direction}（可选 long 只做多 / short 只做空 / both 多空双向）")
    margin_interest = float((body or {}).get("margin_interest", 0.0) or 0.0)

    strat = get_strategy(strategy_name)
    if strat is None:
        raise ValueError(f"未知策略：{strategy_name}")

    df = market.get_bars(source, symbol, interval, limit)
    # 自由选择回测时间范围
    start_date = ((body or {}).get("start_date") or "").strip()
    end_date = ((body or {}).get("end_date") or "").strip()
    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]
    df = df.reset_index(drop=True)
    if len(df) < 20:
        raise ValueError(f"所选时间范围内数据不足（仅 {len(df)} 根K线），请放宽日期或增大K线数量")
    # 参数类型修正
    cleaned = {}
    for p in strat["params"]:
        v = params.get(p["key"], p["default"])
        if v is None:
            v = p["default"]
        cleaned[p["key"]] = float(v) if p["type"] == "float" else int(v)
    position = strat["fn"](df, **cleaned)
    # 只做空 + 只做多策略 = 信号反转（持有->空仓，空仓->开空）
    if direction == "short" and strat.get("long_only", True):
        position = position - 1.0
    result = run_backtest(df, position, initial_capital, fee_rate, interval,
                          leverage=leverage, direction=direction,
                          margin_interest=margin_interest)
    result["strategy"] = {"name": strategy_name, "label": strat["label"],
                          "label_en": strat.get("label_en", strat["label"]),
                          "params": cleaned, "long_only": strat.get("long_only", True)}
    result["direction"] = direction
    result["symbol"] = symbol
    result["interval"] = interval
    result["name"] = _resolve_name(source, symbol)
    result["signal"] = last_signal(df, position)
    return result


def _resolve_name(source: str, symbol: str) -> str:
    """解析标的名称（如 600519 -> 贵州茅台）。"""
    from quant.data.base import get_source
    try:
        src = get_source(source)
        if src is not None:
            name = src.get_name(symbol)
            if name:
                return str(name)
    except Exception:
        pass
    return symbol


def api_quote(query, _body):
    source = query.get("source", ["synthetic"])[0]
    symbol = query.get("symbol", [""])[0]
    q = market.get_quote(source, symbol)
    if q is None:
        raise ValueError("该数据源暂不支持实时报价（请使用模拟数据源，或检查网络）")
    return q


def api_signal(query, _body):
    source = query.get("source", ["synthetic"])[0]
    symbol = query.get("symbol", [""])[0]
    interval = query.get("interval", ["1d"])[0]
    strategy_name = query.get("strategy", ["ma_cross"])[0]
    params = json.loads(query.get("params", ["{}"])[0])
    strat = get_strategy(strategy_name)
    if strat is None:
        raise ValueError(f"未知策略：{strategy_name}")
    df = market.get_bars(source, symbol, interval, 300)
    cleaned = {}
    for p in strat["params"]:
        v = params.get(p["key"], p["default"])
        if v is None:
            v = p["default"]
        cleaned[p["key"]] = float(v) if p["type"] == "float" else int(v)
    position = strat["fn"](df, **cleaned)
    out = last_signal(df, position)
    out["strategy_label"] = strat["label"]
    return out


def api_margin(query, _body):
    """个股两融（融资融券）历史数据。"""
    from quant.margin import get_margin_history
    symbol = query.get("symbol", [""])[0]
    limit = int(query.get("limit", ["250"])[0])
    return get_margin_history(symbol, limit)


def api_suggest(query, _body):
    """按名称/代码/拼音搜索标的。"""
    from quant.suggest import suggest
    return suggest(query.get("q", [""])[0])


def api_name(query, _body):
    """解析标的名称。"""
    from quant.data.base import get_source
    src = get_source(query.get("source", [""])[0])
    symbol = query.get("symbol", [""])[0]
    if src is None:
        raise ValueError(f"未知数据源：{query.get('source', [''])[0]}")
    return {"name": src.get_name(symbol)}


def api_generate_strategy(_query, body):
    """自然语言 -> AI 策略（DeepSeek API）。"""
    prompt = ((body or {}).get("prompt") or "").strip()
    api_key = ((body or {}).get("api_key") or "").strip() or os.environ.get("DEEPSEEK_API_KEY", "").strip()
    model = (body or {}).get("model") or "deepseek-chat"
    if not prompt:
        raise ValueError("请先用一句话描述你的策略，例如：5日均线上穿20日均线买入，下穿卖出")
    if not api_key:
        raise ValueError(
            "请填写 DeepSeek API Key（在 https://platform.deepseek.com 免费注册获取），"
            "或设置环境变量 DEEPSEEK_API_KEY"
        )
    from quant.ai_strategy import generate_strategy, register_generated
    result = generate_strategy(prompt, api_key, model)
    name = "ai_" + uuid.uuid4().hex[:8]
    label = "🤖 " + prompt[:24]
    register_generated(name, label, result["code"], result["params"])
    return {"name": name, "label": label, "code": result["code"], "params": result["params"]}


def _app_version() -> str:
    """应用版本：源码（quant/ 与 web/）最新修改时间指纹。

    前端轮询此接口，版本变化即自动刷新页面 → 更新直接同步到所有访问者。
    """
    import hashlib
    sig = []
    for sub in ("quant", "web"):
        base = os.path.join(ROOT, sub)
        for dirname, _dirs, files in os.walk(base):
            for f in files:
                if f.endswith((".py", ".js", ".css", ".html", ".json")):
                    p = os.path.join(dirname, f)
                    try:
                        sig.append((p, os.path.getmtime(p)))
                    except OSError:
                        pass
    sig.sort(key=lambda x: x[1])
    return hashlib.md5(repr(sig).encode("utf-8")).hexdigest()[:10]


def api_version(_query, _body):
    return {"version": _app_version()}


API_ROUTES = {
    ("GET", "/api/sources"): api_sources,
    ("GET", "/api/strategies"): api_strategies,
    ("POST", "/api/backtest"): api_backtest,
    ("GET", "/api/quote"): api_quote,
    ("GET", "/api/signal"): api_signal,
    ("GET", "/api/margin"): api_margin,
    ("GET", "/api/suggest"): api_suggest,
    ("GET", "/api/name"): api_name,
    ("POST", "/api/generate_strategy"): api_generate_strategy,
    ("GET", "/api/version"): api_version,
}


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "QuantApp/0.1"

    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: str):
        if not os.path.isfile(path):
            self.send_error(404, "Not Found")
            return
        ext = os.path.splitext(path)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png", ".ico": "image/x-icon",
            ".svg": "image/svg+xml",
        }.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        route = API_ROUTES.get(("GET", path))
        if route:
            try:
                return self._send_json(route(query, None))
            except Exception as e:
                return self._send_json({"error": str(e)}, 400)
        # 静态文件
        if path == "/":
            path = "/index.html"
        target = os.path.normpath(os.path.join(WEB_DIR, path.lstrip("/")))
        if target.startswith(WEB_DIR):
            return self._send_file(target)
        self.send_error(403, "Forbidden")

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = None
        if length:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"error": "请求体不是合法 JSON"}, 400)
        route = API_ROUTES.get(("POST", parsed.path))
        if route:
            try:
                return self._send_json(route({}, body))
            except Exception as e:
                return self._send_json({"error": str(e)}, 400)
        self.send_error(404, "Not Found")


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------
def selftest():
    print("== 量化引擎自检 ==")
    from quant.strategies import list_strategies as _ls
    df = market.get_bars("synthetic", "SYN:测试股票", "1d", 500)
    assert len(df) == 500 and list(df.columns) == ["date", "open", "high", "low", "close", "volume"], "K线格式错误"
    print(f"  [OK] 模拟数据源：{len(df)} 根日线，区间 {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")

    for s in _ls():
        entry = get_strategy(s["name"])
        params = {p["key"]: p["default"] for p in s["params"]}
        pos = entry["fn"](df, **params)
        allowed = {0.0, 1.0} if entry.get("long_only", True) else {-1.0, 0.0, 1.0}
        assert len(pos) == len(df) and set(pos.unique()) <= allowed, f"策略 {s['name']} 输出非法"
        direction = "long" if entry.get("long_only", True) else "both"
        res = run_backtest(df, pos, 100_000, 0.0003, "1d", direction=direction)
        m = res["metrics"]
        print(f"  [OK] {s['label']}: 收益 {m['total_return_pct']}% | 夏普 {m['sharpe']} | "
              f"最大回撤 {m['max_drawdown_pct']}% | 交易 {m['num_trades']} 次 | 胜率 {m['win_rate_pct']}%")

    q = market.get_quote("synthetic", "SYN:测试股票")
    assert q and "price" in q, "实时报价失败"
    print(f"  [OK] 实时报价：{q['price']}（{q['change_pct']:+}%）")

    # 指标序列（MA/BOLL/MACD/KDJ/RSI）
    from quant.backtest import compute_indicators
    inds = compute_indicators(df)
    n = len(df)
    for grp in ("ma", "boll", "macd", "kdj", "rsi"):
        for kk, vals in inds[grp].items():
            assert len(vals) == n, f"指标 {grp}.{kk} 长度错误"
    k_last = inds["kdj"]["k"][-1]
    assert k_last is not None and -50 <= k_last <= 150, f"KDJ 数值异常: {k_last}"
    print(f"  [OK] 指标序列: MA/BOLL/MACD/KDJ/RSI 共 15 条，长度与K线一致（KDJ.K={k_last}）")

    # 多空 + 杠杆 + 利息 + 强平模拟
    from quant.strategies import get_strategy as _gs
    pos = _gs("ma_cross_dual")["fn"](df, 5, 20)
    res = run_backtest(df, pos, 100_000, 0.0003, "1d",
                       leverage=2.0, direction="both", margin_interest=0.0835)
    m = res["metrics"]
    assert m["short_trades"] >= 0 and m["leverage_used"] == 2.0
    print(f"  [OK] 多空+2倍杠杆: 收益 {m['total_return_pct']}% | 空单 {m['short_trades']} 笔 | "
          f"强平 {m['margin_call_count']} 次 | 利息 {m['interest_total']}")

    # 两融数据（联网）
    try:
        from quant.margin import get_margin_history
        mg = get_margin_history("600519", 60)
        assert len(mg["dates"]) >= 30
        print(f"  [OK] 两融数据: {mg['name']} 融资余额 {mg['rzye'][-1]} 亿 / 融券余额 {mg['rqye'][-1]} 亿")
    except Exception as e:
        print(f"  [跳过] 两融数据（联网受限）: {e}")

    from quant.storage import Storage
    st = Storage(os.path.join(ROOT, "data", "test.db"))
    st.save("test", "TST", "1d", df.head(100))
    cached = st.load("test", "TST", "1d", limit=100)
    assert cached is not None and len(cached) == 100, "存储缓存失败"
    print("  [OK] SQLite 存储：写入/读取 100 行")
    print("== 自检全部通过 ==")


def main():
    parser = argparse.ArgumentParser(description="量化应用 Web 服务")
    # 云平台（Render/Koyeb/HF 等）会通过环境变量 PORT 指定端口
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print("=" * 52)
    print("  量化应用已启动")
    print(f"  请在浏览器打开：{url}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 52)

    # 后台预热：期货合约表、数据源注册等（避免首次请求卡顿）
    def _warmup():
        try:
            from quant.data.futures import _EM_TABLE
            _EM_TABLE.load()
            print("  [预热完成] 期货主连/合约名称表已加载")
        except Exception:
            pass

    threading.Thread(target=_warmup, daemon=True).start()

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
