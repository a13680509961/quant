/* ============ 多语言支持（中文 / English） ============ */
"use strict";

// 语言字典：键为中文原文（中文即默认语言），值为英文翻译
const I18N_DICT = {
  en: {
    // 品牌与顶栏
    "量化分析工作台": "Quant Studio",
    "实时盯盘已开启": "Live monitor on",
    "实时盯盘已关闭": "Live monitor off",
    // 侧栏分区
    "📡 数据": "📡 Data",
    "🧠 策略": "🧠 Strategy",
    "🤖 AI 生成策略": "🤖 AI Strategy",
    "⚙️ 回测设置": "⚙️ Backtest",
    // 表单标签
    "数据源": "Data source",
    "标的代码 / 名称": "Symbol / name",
    "周期": "Interval",
    "K 线数量": "Bars",
    "策略": "Strategy",
    "用一句话描述你的策略": "Describe your strategy in one sentence",
    "DeepSeek API Key": "DeepSeek API Key",
    "初始资金": "Initial capital",
    "单边手续费率": "Fee rate (per side)",
    "杠杆倍数（两融融资）": "Leverage (margin)",
    "交易方向": "Direction",
    "融资年利率 %": "Margin interest %/yr",
    "开始日期（留空 = 最早）": "Start date (blank = earliest)",
    "结束日期（留空 = 最新）": "End date (blank = latest)",
    // 按钮
    "▶ 运行回测": "▶ Run Backtest",
    "◉ 实时盯盘：开": "◉ Live: ON",
    "○ 实时盯盘：关": "○ Live: OFF",
    "✨ 生成并回测": "✨ Generate & Backtest",
    "🤖 生成中（约 10~30 秒）…": "🤖 Generating (~10-30s)…",
    "查看生成的策略代码": "View generated code",
    // 选项
    "只做多": "Long only",
    "只做空": "Short only",
    "多空双向": "Both",
    // 提示
    "快速上手": "Quick start",
    "① 默认用「模拟数据」离线演示；": "1) Default synthetic data works offline;",
    "② A股/期货/基金/美股可选真实行情（需联网）；": "2) A-shares/futures/funds/US stocks need internet;",
    "③ 想自定义策略？在「AI 生成策略」里用一句话描述；": "3) Describe a strategy in natural language via AI panel;",
    "④ 换策略/调参数后点「运行回测」；": "4) Click Run Backtest after changing settings;",
    "⑤ 滚轮缩放 K 线，拖拽平移，悬停看细节。": "5) Wheel = zoom, drag = pan, hover = details.",
    "只做空时：多空策略只取空头信号；只做多策略自动反转信号（空仓→开空，持有→平空）":
      "Short-only: dual strategies keep only short signals; long-only strategies are inverted (flat→short, holding→cover)",
    // 占位符
    "如 600519、贵州茅台、RB0、00700": "e.g. 600519, AAPL, RB0, 00700",
    "sk-...（留空则读环境变量 DEEPSEEK_API_KEY）": "sk-... (blank = env DEEPSEEK_API_KEY)",
    "例：5日均线上穿20日均线买入，跌破20日均线卖出，亏损3%止损":
      "e.g. Buy when 5-day MA crosses above 20-day MA, sell below, 3% stop-loss",
    // 实时信号条
    "标的": "Symbol",
    "最新价": "Last",
    "涨跌": "Change",
    "最新信号": "Signal",
    "持仓状态": "Position",
    "更新时间": "Updated",
    "持仓中": "Long",
    "做空中": "Short",
    "空仓": "Flat",
    "回测完成": "Backtest done",
    "（信号）": " (signal)",
    // 指标卡
    "总收益": "Total Return",
    "同期基准 {x}%": "Benchmark {x}%",
    "年化收益": "CAGR",
    "按周期年化": "annualized",
    "夏普比率": "Sharpe",
    "越高越稳": "higher = steadier",
    "最大回撤": "Max Drawdown",
    "风险指标": "risk metric",
    "交易次数": "Trades",
    "买卖配对": "paired trades",
    "胜率": "Win Rate",
    "盈利笔数占比": "share of winners",
    "盈亏比": "Profit Factor",
    "总盈 / 总亏": "gross win / loss",
    "平均单笔": "Avg Trade",
    "每笔交易收益": "avg return per trade",
    // 图表区
    "K 线图": "Candlestick",
    "滚轮缩放 · 拖拽平移 · 悬停查看 OHLC 与指标数值":
      "Wheel zoom · drag pan · hover for OHLC & indicators",
    "价格图叠加 MA/BOLL · 副图 MACD/KDJ/RSI":
      "Price overlays: MA/BOLL · Sub-charts: MACD/KDJ/RSI",
    "主图叠加 / 副图窗格，点击开关":
      "Price overlays / sub-chart panes · click to toggle",
    "买入": "Buy",
    "卖出": "Sell",
    "开空": "Short",
    "平空": "Cover",
    "两融资金": "Margin Trading",
    "{name} · 融资/融券余额（亿元）": "{name} · Margin balance (100M CNY)",
    "融资 = 借钱做多 · 融券 = 借券做空；数据来源：东方财富数据中心（仅 A股标的）":
      "Financing = borrow cash to long · Sec-lending = borrow shares to short; data: Eastmoney (A-shares only)",
    "融资余额（左轴）": "Financing balance (left)",
    "融券余额（右轴）": "Sec-lending balance (right)",
    "净值曲线": "Equity Curve",
    "策略 vs 买入持有": "Strategy vs Buy&Hold",
    "策略净值": "Strategy",
    "买入持有": "Buy & Hold",
    "交易明细": "Trades",
    "共 {n} 笔": "{n} total",
    "买入时间": "Entry Time",
    "买入价": "Entry",
    "卖出时间": "Exit Time",
    "卖出价": "Exit",
    "收益率": "Return",
    "持有K线": "Bars",
    "结果": "Result",
    "盈利": "Win",
    "亏损": "Loss",
    "多": "L",
    "空": "S",
    "暂无交易": "No trades",
    // 提示消息
    "回测完成：{s}，总收益 {r}%": "Backtest done: {s}, return {r}%",
    "，杠杆 {l}x": ", leverage {l}x",
    "（强平 {n} 次）": " ({n} margin calls)",
    "策略生成成功，正在回测…": "Strategy generated, running backtest…",
    "生成失败：{e}": "Generation failed: {e}",
    "初始化失败：{e}": "Init failed: {e}",
    "回测失败：{e}": "Backtest failed: {e}",
    "请先用一句话描述你的策略，例如：5日均线上穿20日均线买入，下穿卖出":
      "Describe your strategy first, e.g. Buy when 5-day MA crosses above 20-day MA, sell below",
    // 图表 tooltip
    "开 ": "O ", "高 ": "H ", "低 ": "L ", "收 ": "C ",
    "涨跌 ": "Chg ",
    "量 ": "Vol ",
    "▲ 买入（开多）": "▲ Buy (open long)",
    "▼ 卖出（平多）": "▼ Sell (close long)",
    "▼ 融券卖出（开空）": "▼ Short (open short)",
    "▲ 买券还券（平空）": "▲ Cover (close short)",
    "点击「运行回测」加载数据": "Click Run Backtest to load data",
    "暂无数据": "No data",
    // 信号动作（后端 action_code）
    "买入": "Buy",
    "卖出": "Sell",
    "持有": "Hold",
    "空仓": "Flat",
    "融券卖出": "Short",
    "买券还券": "Cover",
    "做空持有": "Short holding",
    // 语言切换器
    "语言": "Language",
    // 周期选项
    "日线（1d）": "Daily (1d)",
    "小时线（1h）": "Hourly (1h)",
    "15 分钟（15m）": "15 min (15m)",
    "1 分钟（1m）": "1 min (1m)",
    // 两融图
    "融资余额": "Financing balance",
    "融券余额": "Sec-lending balance",
    "（左轴）": " (left)",
    "（右轴）": " (right)",
  },
};

let I18N_LANG = "zh";
window.APP_LOCALE = "zh-CN";

function t(key, params) {
  let text = I18N_LANG === "zh" ? key : (I18N_DICT.en[key] ?? key);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.split("{" + k + "}").join(v);
    }
  }
  return text;
}

/* 常见后端中文错误 -> 英文（正则匹配，顺序有优先级） */
const I18N_ERROR_RULES = [
  [/请填写标的代码/, "Please enter a symbol."],
  [/数据不足（仅 \d+ 根K线）/, "Insufficient data in the selected date range."],
  [/网络不可用/, "Network unavailable."],
  [/无法访问[^，。]*行情/, "Unable to reach the market data service."],
  [/未获取到.*数据/, "No data returned for this symbol."],
  [/请检查联网后重试/, "Please check your internet connection and retry."],
  [/加权指数/, "Weighted index is not available from free sources; use main (6666) or continuous (0) instead."],
  [/无法识别期货代码/, "Unrecognized futures code. Use AG6666 (main), AG7777 (2nd main), AG0 (continuous), CU2506 (contract)."],
  [/请填写 DeepSeek API Key/, "Please enter your DeepSeek API Key (register at platform.deepseek.com) or set env DEEPSEEK_API_KEY."],
  [/API Key 无效/, "Invalid DeepSeek API Key."],
  [/无法连接 DeepSeek/, "Cannot reach the DeepSeek API; check your network."],
  [/生成的代码未通过校验[^。]*/, "The generated code failed validation. Rephrase your request and retry."],
  [/不含 strategy 函数/, "The model output has no strategy function; rephrase and retry."],
  [/未知数据源/, "Unknown data source."],
  [/未知策略/, "Unknown strategy."],
  [/未知交易方向/, "Unknown direction."],
  [/该数据源暂不支持实时报价/, "Real-time quotes are not supported by this source."],
  [/不支持周期[^，。]*/, "Unsupported interval for this source."],
  [/仅支持日线[^。]*/, "Daily bars only for this source."],
  [/最小 5 分钟/, "Minimum interval is 5 minutes."],
  [/行情获取失败/, "Failed to fetch market data."],
  [/请求失败（HTTP \d+）/, "HTTP request failed."],
  [/请填写标的/, "Please enter a symbol."],
  [/不在此数据源支持范围|不在融资融券标的范围/, "Not covered by this data source."],
];

function translateError(msg) {
  if (I18N_LANG === "zh") return msg;
  for (const [re, en] of I18N_ERROR_RULES) {
    if (re.test(msg)) return en;
  }
  return msg; // 未命中保留原文
}

function applyStaticText(root) {
  root = root || document;
  root.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  root.querySelectorAll("[data-i18n-ph]").forEach(el => {
    el.placeholder = t(el.getAttribute("data-i18n-ph"));
  });
  root.querySelectorAll("[data-i18n-title]").forEach(el => {
    el.title = t(el.getAttribute("data-i18n-title"));
  });
}

function setLang(lang) {
  I18N_LANG = lang === "en" ? "en" : "zh";
  window.APP_LOCALE = lang === "en" ? "en-US" : "zh-CN";
  try { localStorage.setItem("quant_lang", I18N_LANG); } catch (e) { /* ignore */ }
  applyStaticText(document);
  document.querySelectorAll("#langZh, #langEn").forEach(b => {
    b.classList.toggle("on", b.id === (lang === "en" ? "langEn" : "langZh"));
  });
  if (typeof window.onLangChange === "function") window.onLangChange(I18N_LANG);
  return I18N_LANG;
}

/* 启动时初始化：URL ?lang=en 优先，其次 localStorage */
(function initLang() {
  let lang = "zh";
  try {
    const q = new URLSearchParams(location.search).get("lang");
    if (q) lang = q;
    else lang = localStorage.getItem("quant_lang") || "zh";
  } catch (e) { /* ignore */ }
  setLang(lang);
})();
