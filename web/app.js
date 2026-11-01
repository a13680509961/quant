/* ============ 量化分析工作台 · 前端逻辑 ============ */
"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  sources: [],
  strategies: [],
  sourceId: "synthetic",
  symbol: "",
  interval: "1d",
  limit: 500,
  strategyName: "ma_cross",
  strategyLabel: "",
  lastParams: {},
  lastCandles: null,
  lastMarkers: null,
  lastIndicators: null,
  lastMetrics: null,
  lastRes: null,
  lastMarginData: null,
  lastQuote: null,
  lastSignal: null,
  ind: {
    ma: true, boll: false, expma: false, bbi: false, sar: false,
    macd: true, kdj: true, rsi: false, wr: false, cci: false,
    obv: false, dmi: false, bias: false, roc: false, psy: false,
    mtm: false, vr: false, trix: false,
  },
  liveOn: true,
  pollTimer: null,
};

const klineChart = new CandlestickChart($("klineChart"));
const equityChart = new LineChart($("equityChart"));
const marginChart = new LineChart($("marginChart"));

/* ---------------- 工具函数 ---------------- */
// 按当前语言取中文/英文标签
const labelOf = (item) =>
  (I18N_LANG === "en" && item && item.label_en) ? item.label_en : (item ? item.label : "");

async function getJSON(url, options) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || data.error) {
    throw new Error(translateError(data.error || `请求失败（${resp.status}）`));
  }
  return data;
}

/* 语言切换后重绘所有动态内容 */
function onLanguageChanged() {
  fillSourceSel();
  fillStrategySel();
  buildParams();
  if (state.lastRes) {
    renderMetrics(state.lastRes.metrics);
    renderKline(state.lastRes);
    renderEquity(state.lastRes);
    renderTrades(state.lastRes.trades);
  }
  if (state.lastMarginData) renderMarginFromData(state.lastMarginData);
  if (state.lastQuote || state.lastSignal) {
    updateLiveStrip(state.lastQuote, state.lastSignal);
  }
  $("liveBtn").textContent = state.liveOn ? t("◉ 实时盯盘：开") : t("○ 实时盯盘：关");
}

let toastTimer = null;
function toast(msg, isError) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "show" + (isError ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ""; }, 3200);
}

function sma(arr, n) {
  const out = new Array(arr.length).fill(null);
  let sum = 0;
  for (let i = 0; i < arr.length; i++) {
    sum += arr[i];
    if (i >= n) sum -= arr[i - n];
    if (i >= n - 1) out[i] = sum / n;
  }
  return out;
}

function rsiValues(arr, n) {
  const out = new Array(arr.length).fill(null);
  let g = 0, l = 0;
  for (let i = 1; i < arr.length; i++) {
    const d = arr[i] - arr[i - 1];
    const gain = Math.max(d, 0), loss = Math.max(-d, 0);
    if (i <= n) { g += gain; l += loss; if (i < n) continue; g /= n; l /= n; }
    else { g = (g * (n - 1) + gain) / n; l = (l * (n - 1) + loss) / n; }
    out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
  }
  return out;
}

function rollMaxMin(arr, n, shift) {
  const hi = new Array(arr.length).fill(null), lo = new Array(arr.length).fill(null);
  for (let i = 0; i < arr.length; i++) {
    const end = i - shift;
    if (end - n + 1 < 0) continue;
    let mx = -Infinity, mn = Infinity;
    for (let j = end - n + 1; j <= end; j++) { mx = Math.max(mx, arr[j]); mn = Math.min(mn, arr[j]); }
    hi[i] = mx; lo[i] = mn;
  }
  return { hi, lo };
}

/* ---------------- 初始化 ---------------- */
async function init() {
  try {
    const [sources, strategies] = await Promise.all([
      getJSON("/api/sources"),
      getJSON("/api/strategies"),
    ]);
    state.sources = sources;
    state.strategies = strategies;
    fillSourceSel();
    fillStrategySel();
    state.sourceId = sources[0] ? sources[0].id : "synthetic";
    onSourceChange();
    buildParams();
    $("runBtn").addEventListener("click", runBacktest);
    $("sourceSel").addEventListener("change", onSourceChange);
    $("strategySel").addEventListener("change", onStrategyChange);
    $("liveBtn").addEventListener("click", toggleLive);
    $("aiBtn").addEventListener("click", aiGenerate);
    initSuggest();
    window.onLangChange = onLanguageChanged;
    // 指标开关
    $("indToggles").addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      const key = btn.dataset.ind;
      state.ind[key] = !state.ind[key];
      btn.classList.toggle("on", state.ind[key]);
      renderChart();
    });
    window.addEventListener("resize", () => { klineChart.render(); equityChart.render(); });
    await runBacktest();  // 首次自动回测，立刻看到效果
    startPolling();
    startVersionWatch();
  } catch (e) {
    toast(t("初始化失败：{e}", { e: translateError(e.message) }), true);
  }
}

/* ---------------- 更新自动同步：版本变化即自动刷新页面 ---------------- */
function startVersionWatch() {
  let first = true;
  setInterval(async () => {
    try {
      const r = await getJSON("/api/version");
      if (first) { state.version = r.version; first = false; return; }
      if (r.version !== state.version) {
        // 后端源码更新：服务已自动重启，刷新页面获取最新版本
        location.reload();
      }
    } catch (e) { /* 服务重启瞬间失败，忽略 */ }
  }, 20000);
}

function fillSourceSel() {
  const sel = $("sourceSel");
  sel.innerHTML = "";
  state.sources.forEach(s => {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = labelOf(s);
    sel.appendChild(opt);
  });
  sel.value = state.sourceId;
}

function onSourceChange() {
  state.sourceId = $("sourceSel").value;
  const src = state.sources.find(s => s.id === state.sourceId);
  // 更新标的建议
  const dl = $("symbolList");
  dl.innerHTML = "";
  (src ? src.default_symbols : []).forEach(sym => {
    const opt = document.createElement("option");
    opt.value = sym;
    dl.appendChild(opt);
  });
  if (!state.symbol && src && src.default_symbols.length) {
    state.symbol = src.default_symbols[0];
    $("symbolInput").value = state.symbol;
  }
  // 按数据源支持度启用/禁用周期
  const ivs = src && src.intervals ? src.intervals : ["1d", "1h", "15m", "1m"];
  const ivSel = $("intervalSel");
  for (const opt of ivSel.options) {
    opt.disabled = !ivs.includes(opt.value);
  }
  if (!ivs.includes(state.interval)) {
    state.interval = ivs[0];
    ivSel.value = ivs[0];
  }
  startPolling();
}

function fillStrategySel() {
  const sel = $("strategySel");
  sel.innerHTML = "";
  state.strategies.forEach(s => {
    const opt = document.createElement("option");
    opt.value = s.name;
    opt.textContent = labelOf(s);
    sel.appendChild(opt);
  });
  sel.value = state.strategyName;
}

function onStrategyChange() {
  state.strategyName = $("strategySel").value;
  buildParams();
}

/* ---------------- 标的名称搜索 ---------------- */
function initSuggest() {
  const input = $("symbolInput");
  const box = $("symbolSuggest");
  let timer = null;

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = input.value.trim();
      if (!q) { box.hidden = true; $("symbolName").textContent = ""; return; }
      try {
        const items = await getJSON("/api/suggest?q=" + encodeURIComponent(q));
        renderSuggest(items);
      } catch (e) { box.hidden = true; }
    }, 300);
  });

  input.addEventListener("focus", () => { if (box.children.length) box.hidden = false; });
  input.addEventListener("blur", () => setTimeout(() => { box.hidden = true; }, 200));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { box.hidden = true; updateNameHint(); }
  });
}

function renderSuggest(items) {
  const box = $("symbolSuggest");
  box.innerHTML = "";
  if (!items.length) { box.hidden = true; return; }
  items.forEach(it => {
    const div = document.createElement("div");
    div.className = "sg-item";
    div.innerHTML =
      `<span class="sg-name">${escapeHtml(it.name)}</span>` +
      `<span class="sg-code">${escapeHtml(it.symbol)}</span>` +
      `<span class="sg-src">${escapeHtml(it.source)}</span>`;
    div.addEventListener("mousedown", (ev) => { ev.preventDefault(); pickSymbol(it); });
    box.appendChild(div);
  });
  box.hidden = false;
}

function pickSymbol(it) {
  state.symbol = it.symbol;
  $("symbolInput").value = it.symbol;
  $("symbolSuggest").hidden = true;
  $("symbolName").textContent = it.name;
  if (it.source !== state.sourceId) {
    $("sourceSel").value = it.source;
    onSourceChange();
    $("symbolInput").value = it.symbol;   // onSourceChange 可能重置输入，再设回
  }
}

async function updateNameHint() {
  const sym = $("symbolInput").value.trim();
  if (!sym) { $("symbolName").textContent = ""; return; }
  try {
    const r = await getJSON(
      `/api/name?source=${encodeURIComponent(state.sourceId)}&symbol=${encodeURIComponent(sym)}`);
    $("symbolName").textContent = r.name && r.name !== sym ? r.name : "";
  } catch (e) { $("symbolName").textContent = ""; }
}

/* 动态生成策略参数输入 */
function buildParams() {
  const strat = state.strategies.find(s => s.name === state.strategyName);
  const box = $("paramBox");
  box.innerHTML = "";
  if (!strat) return;
  strat.params.forEach(p => {
    const label = document.createElement("label");
    label.className = strat.params.length % 2 === 1 ? "half" : "";
    label.innerHTML = `${escapeHtml(labelOf(p))}<input type="number" data-key="${p.key}" data-type="${p.type}"
      value="${p.default}" min="${p.min}" max="${p.max}" step="${p.step ?? 1}">`;
    box.appendChild(label);
  });
}

function currentParams() {
  const out = {};
  document.querySelectorAll("#paramBox input[data-key]").forEach(inp => {
    const t = inp.dataset.type;
    out[inp.dataset.key] = t === "float" ? parseFloat(inp.value) : parseInt(inp.value, 10);
  });
  return out;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/* ---------------- AI 生成策略 ---------------- */
async function aiGenerate() {
  const prompt = $("aiPrompt").value.trim();
  const apiKey = $("apiKeyInput").value.trim();
  const btn = $("aiBtn");
  const box = $("aiBox");
  if (!prompt) {
    toast(t("请先用一句话描述你的策略，例如：5日均线上穿20日均线买入，下穿卖出"), true);
    return;
  }
  btn.disabled = true;
  btn.textContent = t("🤖 生成中（约 10~30 秒）…");
  try {
    const res = await getJSON("/api/generate_strategy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, api_key: apiKey }),
    });
    // 加入策略下拉框并选中
    state.strategies.push({ name: res.name, label: res.label, label_en: res.label, params: res.params });
    const opt = document.createElement("option");
    opt.value = res.name;
    opt.textContent = labelOf(state.strategies[state.strategies.length - 1]);
    $("strategySel").appendChild(opt);
    $("strategySel").value = res.name;
    state.strategyName = res.name;
    buildParams();
    box.hidden = false;
    box.innerHTML = `<details open><summary>${t("查看生成的策略代码")}</summary><pre></pre></details>`;
    box.querySelector("pre").textContent = res.code;
    toast(t("策略生成成功，正在回测…"));
    await runBacktest();
  } catch (e) {
    box.hidden = false;
    box.innerHTML = `<div class="ai-err">⚠ ${escapeHtml(translateError(e.message))}</div>`;
    toast(t("生成失败：{e}", { e: translateError(e.message) }), true);
  } finally {
    btn.disabled = false;
    btn.textContent = t("✨ 生成并回测");
  }
}

/* ---------------- 回测 ---------------- */
async function runBacktest() {
  const btn = $("runBtn");
  btn.disabled = true;
  btn.textContent = "⏳ 回测中…";
  try {
    state.symbol = $("symbolInput").value.trim();
    state.interval = $("intervalSel").value;
    state.limit = parseInt($("limitInput").value, 10) || 500;
    const capital = parseFloat($("capitalInput").value) || 100000;
    const fee = parseFloat($("feeInput").value) || 0;
    const leverage = parseFloat($("leverageInput").value) || 1;
    const direction = $("directionSel").value || "long";
    const marginInterest = (parseFloat($("interestInput").value) || 0) / 100;
    const startDate = $("startDateInput").value || "";
    const endDate = $("endDateInput").value || "";
    if (!state.symbol) throw new Error("请填写标的代码");
    const params = currentParams();

    const res = await getJSON("/api/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: state.sourceId,
        symbol: state.symbol,
        interval: state.interval,
        strategy: state.strategyName,
        params,
        initial_capital: capital,
        fee_rate: fee,
        limit: state.limit,
        leverage,
        direction,
        margin_interest: marginInterest,
        start_date: startDate,
        end_date: endDate,
      }),
    });

    state.lastCandles = res.candles;
    state.lastMarkers = res.markers || [];
    state.lastIndicators = res.indicators || null;
    state.lastMetrics = res.metrics;
    state.lastRes = res;
    state.lastParams = params;
    state.strategyLabel = res.strategy.label;

    renderMetrics(res.metrics);
    renderKline(res);
    renderEquity(res);
    renderTrades(res.trades);
    renderMargin(res);
    const displaySymbol = res.name && res.name !== res.symbol ? `${res.name}（${res.symbol}）` : res.symbol;
    $("symbolName").textContent = res.name && res.name !== res.symbol ? res.name : "";
    state.lastQuote = { symbol: displaySymbol, price: res.signal.last_close };
    state.lastSignal = res.signal;
    updateLiveStrip(state.lastQuote, res.signal);
    $("liveTs").textContent = t("回测完成");
    const extra = res.metrics.leverage_used > 1
      ? t("，杠杆 {l}x", { l: res.metrics.leverage_used }) +
        (res.metrics.margin_call_count ? t("（强平 {n} 次）", { n: res.metrics.margin_call_count }) : "")
      : "";
    toast(t("回测完成：{s}，总收益 {r}%", { s: labelOf(res.strategy), r: res.metrics.total_return_pct }) + extra);
    startPolling();
  } catch (e) {
    toast(t("回测失败：{e}", { e: translateError(e.message) }), true);
  } finally {
    btn.disabled = false;
    btn.textContent = t("▶ 运行回测");
  }
}

/* ---------------- 渲染 ---------------- */
function colorize(el, v) {
  el.classList.remove("up", "down");
  if (v > 0) el.classList.add("up");
  else if (v < 0) el.classList.add("down");
}

function renderMetrics(m) {
  const set = (id, val, color) => {
    const el = $(id);
    el.textContent = val;
    el.classList.remove("up", "down");
    if (color) el.classList.add(color);
  };
  set("mTotal", (m.total_return_pct > 0 ? "+" : "") + m.total_return_pct + "%",
    m.total_return_pct > 0 ? "up" : "down");
  $("mBench").textContent = t("同期基准 {x}%",
    { x: (m.benchmark_return_pct > 0 ? "+" : "") + m.benchmark_return_pct });
  set("mCagr", (m.cagr_pct > 0 ? "+" : "") + m.cagr_pct + "%", m.cagr_pct > 0 ? "up" : "down");
  set("mSharpe", m.sharpe.toFixed(2));
  set("mMaxdd", m.max_drawdown_pct.toFixed(2) + "%", "down");
  set("mTrades", m.num_trades);
  set("mWinrate", m.win_rate_pct.toFixed(1) + "%");
  set("mPf", m.profit_factor.toFixed(2));
  set("mAvg", (m.avg_trade_pct > 0 ? "+" : "") + m.avg_trade_pct.toFixed(2) + "%",
    m.avg_trade_pct > 0 ? "up" : "down");
}

function computeOverlays(strategy, params, candles) {
  const c = candles.close;
  const overlays = [];
  let indicator = null;
  if (strategy === "ma_cross") {
    overlays.push({ name: "MA" + params.fast, color: "#ffb020", values: sma(c, params.fast) });
    overlays.push({ name: "MA" + params.slow, color: "#4f8cff", values: sma(c, params.slow) });
  } else if (strategy === "bollinger_revert") {
    const mid = sma(c, params.period), k = params.k;
    const std = new Array(c.length).fill(null);
    for (let i = 0; i < c.length; i++) {
      if (i < params.period - 1) continue;
      let s = 0;
      for (let j = i - params.period + 1; j <= i; j++) s += (c[j] - mid[i]) ** 2;
      std[i] = Math.sqrt(s / params.period);
    }
    overlays.push({ name: "上轨", color: "rgba(255,122,184,.7)", values: mid.map((v, i) => (v === null || std[i] === null ? null : v + k * std[i])) });
    overlays.push({ name: "中轨", color: "#ffb020", values: mid });
    overlays.push({ name: "下轨", color: "rgba(38,166,154,.7)", values: mid.map((v, i) => (v === null || std[i] === null ? null : v - k * std[i])) });
  } else if (strategy === "breakout") {
    const { hi, lo } = rollMaxMin(c, params.period, 1);
    overlays.push({ name: "前" + params.period + "日高", color: "rgba(255,122,184,.7)", values: hi });
    overlays.push({ name: "前" + params.period + "日低", color: "rgba(38,166,154,.7)", values: lo });
  } else if (strategy === "rsi_reversal") {
    indicator = {
      name: "RSI", color: "#b388ff", values: rsiValues(c, params.period),
      refs: [{ v: params.oversold, color: COLORS.down }, { v: params.overbought, color: COLORS.up }],
    };
  }
  return { overlays, indicator };
}

/* 指标开关：MA/BOLL 叠加价格图，MACD/KDJ/RSI 为副图窗格 */
const IND_COLORS = {
  ma: ["#ffb020", "#ff7ab8", "#4f8cff", "#26a69a"],
  dif: "#ffb020", dea: "#4f8cff", k: "#ffb020", d: "#4f8cff", j: "#b388ff",
  rsi1: "#ffb020", rsi2: "#4f8cff", rsi3: "#b388ff",
};

function renderChart() {
  if (!state.lastCandles) return;
  const ind = state.lastIndicators || {};
  const overlays = [];
  const panes = [];
  const lg = [];

  if (state.ind.ma && ind.ma) {
    overlays.push({ name: "MA5", color: IND_COLORS.ma[0], values: ind.ma.ma5 });
    overlays.push({ name: "MA10", color: IND_COLORS.ma[1], values: ind.ma.ma10 });
    overlays.push({ name: "MA20", color: IND_COLORS.ma[2], values: ind.ma.ma20 });
    overlays.push({ name: "MA60", color: IND_COLORS.ma[3], values: ind.ma.ma60 });
    ["MA5", "MA10", "MA20", "MA60"].forEach((n, k) => lg.push({ name: n, color: IND_COLORS.ma[k] }));
  }
  if (state.ind.boll && ind.boll) {
    overlays.push({ name: "BOLL上", color: "rgba(255,122,184,.7)", values: ind.boll.upper });
    overlays.push({ name: "BOLL中", color: "#ffb020", values: ind.boll.mid });
    overlays.push({ name: "BOLL下", color: "rgba(38,166,154,.7)", values: ind.boll.lower });
    lg.push({ name: "BOLL", color: "#ffb020" });
  }
  if (state.ind.expma && ind.expma) {
    overlays.push({ name: "EXPMA12", color: "#ffb020", values: ind.expma.expma12 });
    overlays.push({ name: "EXPMA50", color: "#4f8cff", values: ind.expma.expma50 });
    lg.push({ name: "EXPMA12", color: "#ffb020" }, { name: "EXPMA50", color: "#4f8cff" });
  }
  if (state.ind.bbi && ind.bbi) {
    overlays.push({ name: "BBI", color: "#b388ff", values: ind.bbi.bbi });
    lg.push({ name: "BBI", color: "#b388ff" });
  }
  if (state.ind.sar && ind.sar) {
    overlays.push({ name: "SAR", color: "#ff7ab8", values: ind.sar.sar, points: true });
    lg.push({ name: "SAR", color: "#ff7ab8" });
  }
  if (state.ind.macd && ind.macd) {
    panes.push({
      name: "MACD(12,26,9)",
      refs: [{ v: 0, color: COLORS.axis, label: "0" }],
      series: [
        { name: "DIF", color: IND_COLORS.dif, values: ind.macd.dif, decimals: 3 },
        { name: "DEA", color: IND_COLORS.dea, values: ind.macd.dea, decimals: 3 },
        { name: "MACD", color: "", type: "bar", values: ind.macd.hist, decimals: 3 },
      ],
    });
    lg.push({ name: "DIF", color: IND_COLORS.dif }, { name: "DEA", color: IND_COLORS.dea });
  }
  if (state.ind.kdj && ind.kdj) {
    panes.push({
      name: "KDJ(9,3,3)",
      refs: [{ v: 20, color: "rgba(139,148,158,.4)", label: "20" },
             { v: 80, color: "rgba(139,148,158,.4)", label: "80" }],
      series: [
        { name: "K", color: IND_COLORS.k, values: ind.kdj.k, decimals: 1 },
        { name: "D", color: IND_COLORS.d, values: ind.kdj.d, decimals: 1 },
        { name: "J", color: IND_COLORS.j, values: ind.kdj.j, decimals: 1 },
      ],
    });
    lg.push({ name: "K", color: IND_COLORS.k }, { name: "D", color: IND_COLORS.d }, { name: "J", color: IND_COLORS.j });
  }
  if (state.ind.rsi && ind.rsi) {
    panes.push({
      name: "RSI(6,12,24)",
      refs: [{ v: 30, color: "rgba(38,166,154,.4)", label: "30" },
             { v: 70, color: "rgba(239,83,80,.4)", label: "70" }],
      series: [
        { name: "RSI6", color: IND_COLORS.rsi1, values: ind.rsi.rsi6, decimals: 1 },
        { name: "RSI12", color: IND_COLORS.rsi2, values: ind.rsi.rsi12, decimals: 1 },
        { name: "RSI24", color: IND_COLORS.rsi3, values: ind.rsi.rsi24, decimals: 1 },
      ],
    });
    lg.push({ name: "RSI6", color: IND_COLORS.rsi1 }, { name: "RSI12", color: IND_COLORS.rsi2 },
      { name: "RSI24", color: IND_COLORS.rsi3 });
  }
  if (state.ind.wr && ind.wr) {
    panes.push({
      name: "WR(14)",
      refs: [{ v: -20, color: "rgba(239,83,80,.4)", label: "-20" },
             { v: -80, color: "rgba(38,166,154,.4)", label: "-80" }],
      series: [{ name: "WR", color: "#ffb020", values: ind.wr.wr14, decimals: 1 }],
    });
    lg.push({ name: "WR", color: "#ffb020" });
  }
  if (state.ind.cci && ind.cci) {
    panes.push({
      name: "CCI(14)",
      refs: [{ v: 100, color: "rgba(239,83,80,.4)", label: "100" },
             { v: -100, color: "rgba(38,166,154,.4)", label: "-100" }],
      series: [{ name: "CCI", color: "#ff7ab8", values: ind.cci.cci14, decimals: 1 }],
    });
    lg.push({ name: "CCI", color: "#ff7ab8" });
  }
  if (state.ind.obv && ind.obv) {
    panes.push({
      name: "OBV",
      series: [{ name: "OBV", color: "#4f8cff", values: ind.obv.obv, decimals: 0 }],
    });
    lg.push({ name: "OBV", color: "#4f8cff" });
  }
  if (state.ind.dmi && ind.dmi) {
    panes.push({
      name: "DMI(14,6)",
      series: [
        { name: "+DI", color: COLORS.up, values: ind.dmi.pdi, decimals: 1 },
        { name: "-DI", color: COLORS.down, values: ind.dmi.mdi, decimals: 1 },
        { name: "ADX", color: "#ffb020", values: ind.dmi.adx, decimals: 1 },
      ],
    });
    lg.push({ name: "+DI", color: COLORS.up }, { name: "-DI", color: COLORS.down },
      { name: "ADX", color: "#ffb020" });
  }
  if (state.ind.bias && ind.bias) {
    panes.push({
      name: "BIAS(6,12,24)",
      refs: [{ v: 0, color: COLORS.axis, label: "0" }],
      series: [
        { name: "BIAS6", color: "#ffb020", values: ind.bias.bias6, decimals: 1 },
        { name: "BIAS12", color: "#4f8cff", values: ind.bias.bias12, decimals: 1 },
        { name: "BIAS24", color: "#b388ff", values: ind.bias.bias24, decimals: 1 },
      ],
    });
    lg.push({ name: "BIAS", color: "#ffb020" });
  }
  if (state.ind.roc && ind.roc) {
    panes.push({
      name: "ROC(12)",
      refs: [{ v: 0, color: COLORS.axis, label: "0" }],
      series: [{ name: "ROC", color: "#ffb020", values: ind.roc.roc12, decimals: 1 }],
    });
    lg.push({ name: "ROC", color: "#ffb020" });
  }
  if (state.ind.psy && ind.psy) {
    panes.push({
      name: "PSY(12)",
      refs: [{ v: 25, color: "rgba(38,166,154,.4)", label: "25" },
             { v: 75, color: "rgba(239,83,80,.4)", label: "75" }],
      series: [{ name: "PSY", color: "#4f8cff", values: ind.psy.psy12, decimals: 1 }],
    });
    lg.push({ name: "PSY", color: "#4f8cff" });
  }
  if (state.ind.mtm && ind.mtm) {
    panes.push({
      name: "MTM(12)",
      refs: [{ v: 0, color: COLORS.axis, label: "0" }],
      series: [{ name: "MTM", color: "#b388ff", values: ind.mtm.mtm12, decimals: 2 }],
    });
    lg.push({ name: "MTM", color: "#b388ff" });
  }
  if (state.ind.vr && ind.vr) {
    panes.push({
      name: "VR(26)",
      refs: [{ v: 40, color: "rgba(38,166,154,.4)", label: "40" },
             { v: 160, color: "rgba(239,83,80,.4)", label: "160" }],
      series: [{ name: "VR", color: "#26a69a", values: ind.vr.vr26, decimals: 1 }],
    });
    lg.push({ name: "VR", color: "#26a69a" });
  }
  if (state.ind.trix && ind.trix) {
    panes.push({
      name: "TRIX(12,9)",
      series: [
        { name: "TRIX", color: "#ffb020", values: ind.trix.trix, decimals: 2 },
        { name: "MATRIX", color: "#4f8cff", values: ind.trix.matrix, decimals: 2 },
      ],
    });
    lg.push({ name: "TRIX", color: "#ffb020" }, { name: "MATRIX", color: "#4f8cff" });
  }

  klineChart.setData(state.lastCandles, state.lastMarkers, overlays, panes);

  const lgEl = $("klineLegend");
  lgEl.innerHTML = lg.map(x => `<span class="lg"><span class="sw" style="background:${x.color}"></span>${x.name}</span>`).join("");
  const hasShort = (state.lastMarkers || []).some(m => m.type === "short" || m.type === "cover");
  lgEl.innerHTML += `<span class="lg"><span class="sw" style="background:${COLORS.up}"></span>${t("买入")}</span>`;
  lgEl.innerHTML += `<span class="lg"><span class="sw" style="background:${COLORS.down}"></span>${t("卖出")}</span>`;
  if (hasShort) {
    lgEl.innerHTML += `<span class="lg"><span class="sw" style="background:${COLORS.down}"></span>${t("开空")}</span>`;
    lgEl.innerHTML += `<span class="lg"><span class="sw" style="background:${COLORS.down}"></span>${t("平空")}</span>`;
  }
}

function renderKline(res) {
  const namePart = res.name && res.name !== res.symbol ? `${res.name}（${res.symbol}）` : res.symbol;
  $("klineTitle").textContent = `${namePart} · ${res.interval} · ${labelOf(res.strategy)}`;
  renderChart();
}

/* 两融资金图（仅 A股标的） */
async function renderMargin(res) {
  const card = $("marginCard");
  const isAStock = state.sourceId === "ashare" && /^\d{6}$/.test((res.symbol || "").trim());
  if (!isAStock) {
    card.hidden = true;
    state.lastMarginData = null;
    return;
  }
  try {
    const data = await getJSON(`/api/margin?symbol=${encodeURIComponent(res.symbol)}`);
    state.lastMarginData = data;
    renderMarginFromData(data);
  } catch (e) {
    card.hidden = true;  // 非两融标的等场景静默隐藏
    state.lastMarginData = null;
  }
}

function renderMarginFromData(data) {
  const card = $("marginCard");
  marginChart.setData(data.dates, [
    { name: t("融资余额"), color: "#4f8cff", values: data.rzye, decimals: 0 },
    { name: t("融券余额"), color: "#ff7ab8", values: data.rqye, axis: "right", decimals: 1 },
  ]);
  $("marginTitle").textContent = t("{name} · 融资/融券余额（亿元）", { name: data.name });
  $("marginLegend").innerHTML =
    `<span class="lg"><span class="sw" style="background:#4f8cff"></span>${t("融资余额")}${t("（左轴）")}</span>` +
    `<span class="lg"><span class="sw" style="background:#ff7ab8"></span>${t("融券余额")}${t("（右轴）")}</span>`;
  card.hidden = false;
}

function renderEquity(res) {
  equityChart.setData(res.equity.dates, [
    { name: t("策略净值"), color: "#4f8cff", values: res.equity.values, fill: true },
    { name: t("买入持有"), color: "#8b949e", values: res.benchmark.values, fill: false },
  ]);
  $("equityLegend").innerHTML =
    `<span class="lg"><span class="sw" style="background:#4f8cff"></span>${t("策略净值")}</span>` +
    `<span class="lg"><span class="sw" style="background:#8b949e"></span>${t("买入持有")}</span>`;
}

function renderTrades(trades) {
  const tbody = $("tradeTable").querySelector("tbody");
  tbody.innerHTML = "";
  $("tradeCount").textContent = t("共 {n} 笔", { n: trades.length });
  $("tradeEmpty").style.display = trades.length ? "none" : "block";
  trades.slice(-60).reverse().forEach((td, k) => {
    const tr = document.createElement("tr");
    const r = td.return_pct;
    const sign = r > 0 ? "+" : "";
    const isShort = (td.side_code || td.side) === "short" || td.side === "做空";
    const sideTag = isShort
      ? `<span class="tag" style="background:rgba(38,166,154,.15);color:#26a69a">${t("空")}</span>`
      : `<span class="tag" style="background:rgba(239,83,80,.15);color:#ef5350">${t("多")}</span>`;
    tr.innerHTML = `
      <td>${trades.length - k}</td>
      <td>${sideTag} ${td.entry_date}</td><td>${td.entry_price}</td>
      <td>${td.exit_date}</td><td>${td.exit_price}</td>
      <td class="${r > 0 ? "up" : "down"}">${sign}${r}%</td>
      <td>${td.bars}</td>
      <td><span class="tag ${td.win ? "win" : "loss"}">${td.win ? t("盈利") : t("亏损")}</span></td>`;
    tbody.appendChild(tr);
  });
}

/* ---------------- 实时盯盘 ---------------- */
function updateLiveStrip(quote, signal, symbol) {
  if (symbol !== undefined) $("liveSymbol").textContent = symbol;
  if (quote) state.lastQuote = quote;
  if (signal) state.lastSignal = signal;
  if (quote && quote.price !== undefined && quote.price !== null) {
    const p = $("livePrice");
    p.textContent = fmtNum(quote.price, quote.price < 10 ? 4 : 2);
    const chg = $("liveChange");
    if (quote.change_pct !== null && quote.change_pct !== undefined) {
      chg.textContent = (quote.change_pct > 0 ? "+" : "") + quote.change_pct + "%";
      chg.className = "v " + (quote.change_pct > 0 ? "up" : quote.change_pct < 0 ? "down" : "");
    }
  }
  if (signal) {
    const a = $("liveAction");
    const actionKey = {
      buy: "买入", sell: "卖出", hold: "持有", flat: "空仓",
      short_open: "融券卖出", short_cover: "买券还券", short_hold: "做空持有",
    }[signal.action_code] || signal.action;
    a.textContent = t(actionKey);
    const clsMap = { buy: "buy", sell: "sell", hold: "hold", flat: "",
      short_open: "sell", short_cover: "buy", short_hold: "sell" };
    a.className = "v badge " + (clsMap[signal.action_code] || "");
    $("livePos").textContent = signal.position === 1 ? t("持仓中") : signal.position === -1 ? t("做空中") : t("空仓");
    if (signal.bar_time) $("liveTs").textContent = signal.bar_time + t("（信号）");
  }
}

function toggleLive() {
  state.liveOn = !state.liveOn;
  const btn = $("liveBtn");
  const badge = $("liveBadge");
  const txt = $("liveBadgeText");
  if (state.liveOn) {
    btn.textContent = t("◉ 实时盯盘：开");
    badge.classList.remove("off");
    txt.textContent = t("实时盯盘已开启");
    startPolling();
    pollOnce();
  } else {
    btn.textContent = t("○ 实时盯盘：关");
    badge.classList.add("off");
    txt.textContent = t("实时盯盘已关闭");
    clearInterval(state.pollTimer);
  }
}

function startPolling() {
  clearInterval(state.pollTimer);
  if (!state.liveOn || !state.symbol) return;
  const src = state.sources.find(s => s.id === state.sourceId);
  const ms = src && src.requires_network ? 20000 : 3000;
  state.pollTimer = setInterval(pollOnce, ms);
}

async function pollOnce() {
  if (!state.liveOn || !state.symbol) return;
  const params = encodeURIComponent(JSON.stringify(state.lastParams || currentParams()));
  const base = `/api/signal?source=${encodeURIComponent(state.sourceId)}` +
    `&symbol=${encodeURIComponent(state.symbol)}&interval=${encodeURIComponent(state.interval)}` +
    `&strategy=${encodeURIComponent(state.strategyName)}&params=${params}`;
  try {
    const [q, sig] = await Promise.all([
      getJSON(`/api/quote?source=${encodeURIComponent(state.sourceId)}&symbol=${encodeURIComponent(state.symbol)}`),
      getJSON(base),
    ]);
    updateLiveStrip(q, sig);
  } catch (e) {
    // 网络源瞬时失败时不打扰用户
  }
}

/* ---------------- 启动 ---------------- */
init();
