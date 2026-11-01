# -*- coding: utf-8 -*-
"""AI 生成策略：调用 DeepSeek 大模型，把自然语言需求变成可回测的策略代码。

流程：
    1. 构造提示词，调用 DeepSeek chat/completions 接口（纯标准库 urllib）；
    2. 清洗返回的代码（去 markdown 围栏）；
    3. 在子进程里用受限环境校验代码（超时保护），通过后注册进策略库。
校验只允许纯计算：pandas / numpy / 内置指标函数，禁止网络、文件、系统调用。
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYSTEM_PROMPT = """你是一名严谨的量化策略工程师。根据用户的需求，输出一个可直接运行的 Python 策略。

严格要求：
1. 只输出 Python 代码本身，不要任何解释文字、不要 markdown 代码块标记。
2. 必须定义一个函数：
   def strategy(df, fast=5, slow=20):   # 参数名与默认值必须和 PARAMS 一致
       入参 df 是 pandas DataFrame，固定列：date(str), open, high, low, close, volume（数值列，按时间升序）。
       返回与 df 等长的 Series，值只能是 0（空仓）或 1（持有，长仓单边），类型可为 int/float。
3. 必须定义参数表（可留空列表 []）：
   PARAMS = [{"key": "fast", "label": "快线周期", "type": "int", "default": 5, "min": 1, "max": 60, "step": 1},
             {"key": "slow", "label": "慢线周期", "type": "int", "default": 20, "min": 2, "max": 120, "step": 1}]
   type 只能是 "int" 或 "float"。
4. 可用工具（已预置，无需 import）：
   pd（pandas）、np（numpy）、math，以及指标函数：
   sma(series, n)、ema(series, n)、rsi(close, n) 返回 0~100、
   macd(close, fast, slow, signal) 返回 (dif, dea, hist) 三个 Series、
   bollinger(close, n, k) 返回 (mid, upper, lower) 三个 Series、atr(df, n)。
   也可直接用 df['close'].rolling(n).mean() 等 pandas 运算。
5. 禁止：网络请求、文件读写、input/print、exec/eval、import os/sys/subprocess 等任何非纯计算操作。
6. 代码必须在数据长度 >= 30 的任意 df 上都能运行；rolling 前期的 NaN 要妥善处理
   （如用比较运算（NaN > x 为 False）或 .fillna(0)，保证返回值无 NaN）。
7. 若需要止损止盈，用简单的状态循环（逐行 for 循环）实现即可，不要复杂化。
"""

_HARNESS_TEMPLATE = '''# -*- coding: utf-8 -*-
import json, sys, traceback
sys.path.insert(0, r"{ROOT}")
import numpy as np
import pandas as pd
import math
from quant.indicators import sma, ema, rsi, macd, bollinger, atr
from quant.ai_strategy import _SAFE_BUILTINS

try:
    with open(r"{CODE_PATH}", encoding="utf-8") as _f:
        _code = _f.read()
    ns = {
        "__builtins__": dict(_SAFE_BUILTINS),
        "pd": pd, "np": np, "math": math,
        "sma": sma, "ema": ema, "rsi": rsi,
        "macd": macd, "bollinger": bollinger, "atr": atr,
    }
    exec(compile(_code, "<ai_strategy>", "exec"), ns)
    fn = ns.get("strategy")
    if not callable(fn):
        raise ValueError("缺少 strategy 函数")

    # 构造 60 根模拟K线做冒烟测试
    np.random.seed(7)
    n = 60
    close = 20 * np.exp(np.cumsum(np.random.normal(0.0003, 0.012, n)))
    df = pd.DataFrame({
        "date": pd.date_range(end=pd.Timestamp.now().floor("D"), periods=n).strftime("%Y-%m-%d"),
        "open": close * (1 + np.random.normal(0, 0.004, n)),
        "high": close * (1 + abs(np.random.normal(0, 0.008, n))),
        "low": close * (1 - abs(np.random.normal(0, 0.008, n))),
        "close": close,
        "volume": np.random.uniform(1e5, 2e6, n),
    })
    pos = pd.Series(fn(df))
    if len(pos) != len(df):
        raise ValueError("返回长度与K线数量不一致")
    if pos.isna().any():
        raise ValueError("返回值含 NaN，请处理 rolling 前期的空值")
    vals = set(pd.unique(pos))
    if not vals <= {0, 1, 0.0, 1.0, True, False, np.int64(0), np.int64(1)}:
        raise ValueError("返回值只能是 0（空仓）或 1（持有），当前为: " + str(vals))
    params = ns.get("PARAMS") or []
    for p in params:
        assert isinstance(p, dict) and p.get("key") and p.get("label"), "PARAMS 格式错误"
        assert p.get("type") in ("int", "float"), "PARAMS.type 只能是 int/float"
        assert p.get("default") is not None, "PARAMS 缺少 default"
        assert p.get("min") is not None and p.get("max") is not None, "PARAMS 缺少 min/max"
    print(json.dumps({"ok": True, "params": params}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
'''

def _safe_import(name, globals_=None, locals_=None, fromlist=(), level=0):
    """只允许导入白名单模块（pandas/numpy/math/quant.*），其余一律拒绝。"""
    if name == "pandas":
        return pd
    if name == "numpy":
        return np
    if name == "math":
        return math
    if name == "quant" or name.startswith("quant."):
        import importlib
        return importlib.import_module(name)
    raise ImportError(f"策略代码禁止导入模块 {name}（只允许 pandas/numpy/math/quant.indicators）")


_SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "sum": sum, "round": round,
    "len": len, "range": range, "enumerate": enumerate, "zip": zip,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "str": str, "int": int, "float": float, "bool": bool,
    "True": True, "False": False, "None": None, "isinstance": isinstance,
    "sorted": sorted, "reversed": reversed, "any": any, "all": all,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "print": print, "type": type, "globals": globals, "locals": locals,
    "__import__": _safe_import,
}


def strip_fences(text: str) -> str:
    t = (text or "").strip()
    lines = t.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _exec_namespace():
    from . import indicators as ta
    return {
        "__builtins__": dict(_SAFE_BUILTINS),
        "pd": pd, "np": np, "math": math, "ta": ta,
        "sma": ta.sma, "ema": ta.ema, "rsi": ta.rsi,
        "macd": ta.macd, "bollinger": ta.bollinger, "atr": ta.atr,
    }


def validate_code(code: str, timeout: int = 20) -> dict:
    """在受限环境校验策略代码。返回 {ok, params} 或 {ok: False, error}。"""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".py", prefix="ai_strategy_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        harness = _HARNESS_TEMPLATE.replace("{ROOT}", ROOT).replace("{CODE_PATH}", path)
        proc = subprocess.run(
            [sys.executable, "-c", harness],
            capture_output=True, text=True, timeout=timeout,
        )
        lines = (proc.stdout or "").strip().splitlines()
        last = lines[-1] if lines else ""
        try:
            result = json.loads(last)
            if isinstance(result, dict) and ("ok" in result):
                return result
        except json.JSONDecodeError:
            pass
        err = ((proc.stderr or "").strip() or last)[-400:]
        return {"ok": False, "error": f"代码执行异常：{err}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "代码运行超时（可能存在死循环）"}
    except OSError:
        # 受限环境无法启动子进程时，退回进程内校验
        return _validate_in_process(code)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _validate_in_process(code: str) -> dict:
    try:
        ns = _exec_namespace()
        exec(compile(code, "<ai_strategy>", "exec"), ns)
        fn = ns.get("strategy")
        if not callable(fn):
            return {"ok": False, "error": "缺少 strategy 函数"}
        n = 60
        close = 20 * np.exp(np.cumsum(np.random.default_rng(7).normal(0.0003, 0.012, n)))
        df = pd.DataFrame({
            "date": [f"2024-01-{i % 28 + 1:02d}" for i in range(n)],
            "open": close, "high": close * 1.01, "low": close * 0.99,
            "close": close, "volume": np.full(n, 1e5),
        })
        pos = pd.Series(fn(df))
        if len(pos) != len(df):
            return {"ok": False, "error": "返回长度与K线数量不一致"}
        if pos.isna().any():
            return {"ok": False, "error": "返回值含 NaN，请处理 rolling 前期的空值"}
        if not set(pd.unique(pos)) <= {0, 1, 0.0, 1.0, True, False}:
            return {"ok": False, "error": "返回值只能是 0/1"}
        return {"ok": True, "params": ns.get("PARAMS") or []}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def register_generated(name: str, label: str, code: str, params: list) -> None:
    """把已校验过的代码注册进策略库。"""
    ns = _exec_namespace()
    exec(compile(code, "<ai_strategy>", "exec"), ns)
    fn = ns.get("strategy")
    if not callable(fn):
        raise ValueError("代码中未找到 strategy 函数")
    from .strategies import register
    register(name, label, list(params), fn)


def call_deepseek(prompt: str, api_key: str, model: str = "deepseek-chat") -> str:
    """调用 DeepSeek 对话接口，返回模型文本。"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 2048,
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=150) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError("DeepSeek API Key 无效或未授权，请到 platform.deepseek.com 核对后重试")
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise ValueError(f"DeepSeek 接口返回 HTTP {e.code}：{detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"无法连接 DeepSeek API（{type(e).__name__}），请检查网络后重试") from e
    choices = (data or {}).get("choices") or []
    if not choices:
        raise ValueError("DeepSeek 未返回内容：" + json.dumps(data, ensure_ascii=False)[:200])
    return choices[0].get("message", {}).get("content") or ""


def generate_strategy(prompt: str, api_key: str, model: str = "deepseek-chat") -> dict:
    """自然语言 -> 策略代码（含校验）。返回 {code, params}。"""
    content = call_deepseek(prompt, api_key, model)
    code = strip_fences(content)
    if "def strategy" not in code:
        raise ValueError("模型返回内容不含 strategy 函数，请换个描述再试")
    result = validate_code(code)
    if not result.get("ok"):
        raise ValueError(f"生成的代码未通过校验：{result.get('error')}。请换个描述重试")
    return {"code": code, "params": result.get("params") or []}
