/* ============ 轻量 Canvas 图表引擎（零依赖） ============ */
"use strict";

const COLORS = {
  up: "#ef5350", down: "#26a69a", accent: "#4f8cff",
  gold: "#ffb020", purple: "#b388ff", pink: "#ff7ab8",
  grid: "rgba(139,148,158,.12)", axis: "#8b949e", text: "#c9d1d9",
  tooltipBg: "rgba(13,17,23,.94)", tooltipBorder: "#3b465a",
};

function fmtNum(v, d) {
  if (v === null || v === undefined || !isFinite(v)) return "--";
  return Number(v).toLocaleString((window.APP_LOCALE || "zh-CN"), {
    minimumFractionDigits: d, maximumFractionDigits: d,
  });
}
// 多语言：存在 i18n 的 t 时使用翻译，否则原样
const T = (k) => (window.t ? window.t(k) : k);
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(50, rect.width), h = Math.max(60, rect.height);
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { w, h, ctx };
}

function niceScale(min, max, ticks) {
  if (!isFinite(min) || !isFinite(max)) return { min: 0, max: 1, step: 1 };
  if (max - min < 1e-12) { max += 1e-9; min -= 1e-9; }
  const raw = (max - min) / ticks;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  return { min: Math.floor(min / step) * step, max: Math.ceil(max / step) * step, step };
}

function drawGrid(ctx, x0, y0, w, h, scale, fmt, opts) {
  opts = opts || {};
  ctx.strokeStyle = opts.color || COLORS.grid;
  if (opts.dashed) ctx.setLineDash([3, 4]);
  ctx.fillStyle = COLORS.axis;
  ctx.font = "11px Segoe UI, Microsoft YaHei, sans-serif";
  ctx.textAlign = opts.alignRight ? "right" : "left";
  ctx.textBaseline = "middle";
  const v = scale.step;
  let first = Math.ceil(scale.min / v) * v;
  for (; first <= scale.max + 1e-9; first += v) {
    const y = y0 + h - ((first - scale.min) / (scale.max - scale.min)) * h;
    if (y < y0 - 1 || y > y0 + h + 1) continue;
    ctx.beginPath();
    ctx.moveTo(x0, y);
    ctx.lineTo(x0 + w, y);
    ctx.stroke();
    const tx = opts.alignRight ? x0 + w - 6 : x0 + 6;
    ctx.fillText(fmt(first), tx, y - 8);
  }
  if (opts.dashed) ctx.setLineDash([]);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/* ======================================================================
 * K 线图：主图 K 线 + 叠加线 + 买卖标记 + 成交量 + 可选副图指标
 * ====================================================================== */
class CandlestickChart {
  constructor(canvas) {
    this.canvas = canvas;
    this.candles = null;
    this.markers = [];        // [{i, type: buy|sell|short|cover, price, date}]
    this.overlays = [];       // [{name, color, values: []}]  价格图叠加线
    this.panes = [];          // [{name, refs:[{v,color,label}], series:[{name,color,values,type:'line'|'bar',width,decimals}]}]
    this.offset = 0;          // 可视窗口起点
    this.count = 120;         // 可视K线数
    this.hover = -1;
    this._drag = null;
    this._bind();
  }

  _bind() {
    const cv = this.canvas;
    cv.addEventListener("wheel", (e) => {
      if (!this.candles) return;
      e.preventDefault();
      const n = this.candles.dates.length;
      const factor = e.deltaY > 0 ? 1.25 : 1 / 1.25;
      let count = clamp(Math.round(this.count * factor), 30, n);
      const anchorAbs = this.hover >= 0 ? this.hover : this.offset + this.count - 1;
      const anchorRel = anchorAbs - this.offset;
      this.offset = clamp(anchorAbs - Math.round(anchorRel * count / Math.max(1, this.count)), 0, n - count);
      this.count = count;
      this.render();
    }, { passive: false });

    cv.addEventListener("mousedown", (e) => {
      if (!this.candles) return;
      // 底部全景条：点击定位 + 左右拖动
      if (this._overviewHit(e)) {
        const n = this.candles.dates.length;
        const rect = this.canvas.getBoundingClientRect();
        const bands = this._bands();
        const mx = e.clientX - rect.left;
        const frac = clamp((mx - bands.plotX) / bands.plotW, 0, 1);
        const center = Math.round(frac * (n - 1));
        this.offset = clamp(center - Math.floor(this.count / 2), 0, Math.max(0, n - this.count));
        this._drag = { x: e.clientX, offset: this.offset, overview: true };
        this.render();
        return;
      }
      this._drag = { x: e.clientX, offset: this.offset };
    });
    window.addEventListener("mousemove", (e) => {
      if (this._drag) {
        const dx = e.clientX - this._drag.x;
        const n = this.candles.dates.length;
        const plotW = this._plotW();
        const perBar = this._drag.overview ? plotW / n : plotW / this.count;
        const bars = Math.round(-dx / perBar);
        if (bars) {
          this.offset = clamp(this._drag.offset + bars, 0, n - this.count);
          this._drag.x = e.clientX;
          this._drag.offset = this.offset;
          this.render();
        }
      }
      // 光标反馈：拖动/缩略条/十字
      if (this._drag) this.canvas.style.cursor = "grabbing";
      else if (this._overviewHit(e)) this.canvas.style.cursor = "pointer";
      else this.canvas.style.cursor = "crosshair";
      if (this.canvas.getBoundingClientRect().width) this.renderHover(e);
    });
    window.addEventListener("mouseup", () => { this._drag = null; });
    cv.addEventListener("mouseleave", () => {
      if (this.hover !== -1) { this.hover = -1; this.render(); }
    });

    // ---- 触屏支持（手机/平板）：单指拖动平移 + 点按查看，双指捏合缩放 ----
    let touchPts = [];
    cv.addEventListener("touchstart", (e) => {
      if (!this.candles) return;
      touchPts = [...e.touches].map(t => ({ x: t.clientX, y: t.clientY }));
      if (touchPts.length === 1) {
        const pt = { clientX: touchPts[0].x, clientY: touchPts[0].y };
        // 底部全景条：点击定位 + 左右拖动
        if (this._overviewHit(pt)) {
          const n = this.candles.dates.length;
          const rect = this.canvas.getBoundingClientRect();
          const bands = this._bands();
          const mx = touchPts[0].x - rect.left;
          const frac = clamp((mx - bands.plotX) / bands.plotW, 0, 1);
          const center = Math.round(frac * (n - 1));
          this.offset = clamp(center - Math.floor(this.count / 2), 0, Math.max(0, n - this.count));
          this._drag = { x: touchPts[0].x, offset: this.offset, overview: true };
          this.render();
        } else {
          // 点按位置显示十字线与数据
          const rect = this.canvas.getBoundingClientRect();
          const bands = this._bands();
          const mx = touchPts[0].x - rect.left;
          const win = this._window();
          if (mx >= bands.plotX && mx <= bands.plotX + bands.plotW) {
            const bw = bands.plotW / win.count;
            const idx = win.start + Math.floor((mx - bands.plotX) / bw);
            if (idx !== this.hover) {
              this.hover = clamp(idx, 0, this.candles.dates.length - 1);
              this.render();
            }
          }
          this._drag = { x: touchPts[0].x, offset: this.offset };
        }
      }
    }, { passive: true });

    cv.addEventListener("touchmove", (e) => {
      if (!this.candles) return;
      const pts = [...e.touches].map(t => ({ x: t.clientX, y: t.clientY }));
      const n = this.candles.dates.length;
      if (pts.length === 2 && touchPts.length === 2) {
        // 双指捏合缩放
        const d0 = Math.hypot(touchPts[0].x - touchPts[1].x, touchPts[0].y - touchPts[1].y);
        const d1 = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
        if (d0 > 10 && d1 > 10) {
          const factor = d0 / d1;
          let count = clamp(Math.round(this.count * factor), 30, n);
          const anchorAbs = this.hover >= 0 ? this.hover : this.offset + this.count - 1;
          const anchorRel = anchorAbs - this.offset;
          this.offset = clamp(anchorAbs - Math.round(anchorRel * count / Math.max(1, this.count)), 0, n - count);
          this.count = count;
          this.render();
        }
      } else if (pts.length === 1 && this._drag) {
        // 单指拖动平移
        const dx = pts[0].x - this._drag.x;
        const plotW = this._plotW();
        const perBar = this._drag.overview ? plotW / n : plotW / this.count;
        const bars = Math.round(-dx / perBar);
        if (bars) {
          this.offset = clamp(this._drag.offset + bars, 0, n - this.count);
          this._drag.x = pts[0].x;
          this._drag.offset = this.offset;
          this.render();
        }
      }
      touchPts = pts;
      if (e.cancelable) e.preventDefault();
    }, { passive: false });

    cv.addEventListener("touchend", () => { touchPts = []; this._drag = null; });
  }

  setData(candles, markers, overlays, panes) {
    this.candles = candles || { dates: [], open: [], high: [], low: [], close: [], volume: [] };
    this.markers = markers || [];
    this.overlays = overlays || [];
    this.panes = panes || [];
    const n = this.candles.dates.length;
    this.count = clamp(this.count, 30, Math.max(30, n));
    this.offset = clamp(n - this.count, 0, Math.max(0, n - this.count));
    this.hover = -1;
    this.render();
  }

  _plotW() {
    const rect = this.canvas.getBoundingClientRect();
    return Math.max(50, rect.width - 8 - 64); // padL + padR
  }

  _overviewHit(e) {
    if (!this.candles || !this.candles.dates.length) return false;
    const rect = this.canvas.getBoundingClientRect();
    const bands = this._bands();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    return y >= bands.overview.y0 && y <= bands.overview.y0 + bands.overview.h &&
      x >= bands.plotX && x <= bands.plotX + bands.plotW;
  }

  _bands() {
    const rect = this.canvas.getBoundingClientRect();
    const w = rect.width, h = rect.height;
    const padL = 8, padR = 64, padT = 10, padB = 22;
    const gap = 6;
    let y = h - padB;
    const bands = {};
    // 底部全景缩略条（可拖动窗格，左右拉动K线）
    const ovH = 18;
    bands.overview = { y0: y - ovH, h: ovH };
    y -= ovH + gap;
    const volH = h * 0.14;
    bands.volume = { y0: y - volH, h: volH };
    y -= volH + gap;
    // 副图指标窗格（自下而上分配）
    const panes = this.panes || [];
    bands.paneBands = [];
    const avail = y - padT - gap * panes.length;
    const paneH = Math.min(h * 0.15, avail / Math.max(1, panes.length));
    for (let i = panes.length - 1; i >= 0; i--) {
      bands.paneBands.unshift({ y0: y - paneH, h: paneH, pane: panes[i] });
      y -= paneH + gap;
    }
    bands.price = { y0: padT, h: Math.max(60, y - padT) };
    bands.plotX = padL;
    bands.plotW = w - padL - padR;
    bands.padL = padL; bands.padR = padR; bands.padT = padT; bands.padB = padB;
    return bands;
  }

  _window() {
    const n = this.candles.dates.length;
    if (!n) return { start: 0, end: 0 };
    const count = Math.min(this.count, n);
    const start = clamp(this.offset, 0, n - count);
    return { start, count, end: start + count };
  }

  _priceRange(win) {
    let lo = Infinity, hi = -Infinity;
    const c = this.candles;
    for (let i = win.start; i < win.end; i++) {
      lo = Math.min(lo, c.low[i]); hi = Math.max(hi, c.high[i]);
    }
    this.overlays.forEach(o => {
      for (let i = win.start; i < win.end; i++) {
        const v = o.values[i];
        if (v !== null && v !== undefined && !isNaN(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      }
    });
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    const pad = (hi - lo) * 0.06 || 1;
    return { min: lo - pad, max: hi + pad };
  }

  render() {
    const { w, h, ctx } = setupCanvas(this.canvas);
    if (!this.candles || !this.candles.dates.length) {
      ctx.fillStyle = COLORS.axis;
      ctx.font = "13px Segoe UI, Microsoft YaHei, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(T("点击「运行回测」加载数据"), w / 2, h / 2);
      return;
    }
    const bands = this._bands();
    const win = this._window();
    const n = this.candles.dates.length;
    const count = win.count;
    if (!count) return;
    const bw = bands.plotW / count;
    const cw = Math.max(1, bw * 0.62);

    const xAt = (i) => bands.plotX + (i - win.start + 0.5) * bw;

    // ---- 主图网格与刻度 ----
    const priceRange = this._priceRange(win);
    const pScale = niceScale(priceRange.min, priceRange.max, 5);
    const pb = bands.price;
    drawGrid(ctx, bands.plotX, pb.y0, bands.plotW, pb.h, pScale,
      (v) => fmtNum(v, v >= 1000 ? 0 : 2), { alignRight: true });

    // ---- K 线 + 影线 ----
    const c = this.candles;
    for (let i = win.start; i < win.end; i++) {
      const x = xAt(i);
      const yOf = (v) => pb.y0 + pb.h - ((v - pScale.min) / (pScale.max - pScale.min)) * pb.h;
      const isUp = c.close[i] >= c.open[i];
      ctx.strokeStyle = isUp ? COLORS.up : COLORS.down;
      ctx.fillStyle = ctx.strokeStyle;
      // 影线
      ctx.beginPath();
      ctx.moveTo(x, yOf(c.high[i]));
      ctx.lineTo(x, yOf(c.low[i]));
      ctx.stroke();
      // 实体
      const yO = yOf(c.open[i]), yC = yOf(c.close[i]);
      const top = Math.min(yO, yC), bh = Math.max(1, Math.abs(yC - yO));
      ctx.fillRect(x - cw / 2, top, cw, bh);
    }

    // ---- 叠加线 / 散点（SAR 等）----
    this.overlays.forEach(o => {
      if (o.points) {
        ctx.fillStyle = o.color;
        for (let i = win.start; i < win.end; i++) {
          const v = o.values[i];
          if (v === null || v === undefined || isNaN(v)) continue;
          const x = xAt(i);
          const y = pb.y0 + pb.h - ((v - pScale.min) / (pScale.max - pScale.min)) * pb.h;
          ctx.beginPath();
          ctx.arc(x, y, 1.6, 0, Math.PI * 2);
          ctx.fill();
        }
        return;
      }
      ctx.strokeStyle = o.color;
      ctx.lineWidth = o.width || 1.4;
      ctx.beginPath();
      let started = false;
      for (let i = win.start; i < win.end; i++) {
        const v = o.values[i];
        if (v === null || v === undefined || isNaN(v)) continue;
        const x = xAt(i);
        const y = pb.y0 + pb.h - ((v - pScale.min) / (pScale.max - pScale.min)) * pb.h;
        if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
      }
      ctx.stroke();
    });

    // ---- 买卖/开平标记 ----
    this.markers.forEach(m => {
      if (m.i < win.start || m.i >= win.end) return;
      const x = xAt(m.i);
      const yOf = (v) => pb.y0 + pb.h - ((v - pScale.min) / (pScale.max - pScale.min)) * pb.h;
      if (m.type === "buy") {
        const y = yOf(c.low[m.i]) + 14;
        ctx.fillStyle = COLORS.up;
        ctx.beginPath();
        ctx.moveTo(x, y - 5); ctx.lineTo(x - 5, y + 4); ctx.lineTo(x + 5, y + 4);
        ctx.closePath(); ctx.fill();
        ctx.fillStyle = COLORS.up;
        ctx.font = "bold 10px Segoe UI, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("B", x, y + 1);
      } else if (m.type === "sell") {
        const y = yOf(c.high[m.i]) - 14;
        ctx.fillStyle = COLORS.down;
        ctx.beginPath();
        ctx.moveTo(x, y + 5); ctx.lineTo(x - 5, y - 4); ctx.lineTo(x + 5, y - 4);
        ctx.closePath(); ctx.fill();
        ctx.fillStyle = COLORS.down;
        ctx.font = "bold 10px Segoe UI, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("S", x, y - 1);
      } else if (m.type === "short") {   // 融券开空
        const y = yOf(c.high[m.i]) - 14;
        ctx.fillStyle = COLORS.down;
        ctx.beginPath();
        ctx.moveTo(x, y + 5); ctx.lineTo(x - 5, y - 4); ctx.lineTo(x + 5, y - 4);
        ctx.closePath(); ctx.fill();
        ctx.fillStyle = COLORS.down;
        ctx.font = "bold 10px Segoe UI, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("空", x, y - 1);
      } else if (m.type === "cover") {   // 买券平空
        const y = yOf(c.low[m.i]) + 14;
        ctx.fillStyle = COLORS.down;
        ctx.beginPath();
        ctx.moveTo(x, y - 5); ctx.lineTo(x - 5, y + 4); ctx.lineTo(x + 5, y + 4);
        ctx.closePath(); ctx.fill();
        ctx.fillStyle = COLORS.down;
        ctx.font = "bold 10px Segoe UI, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("平", x, y + 1);
      }
    });

    // ---- 成交量 ----
    const vb = bands.volume;
    let vmax = 0;
    for (let i = win.start; i < win.end; i++) vmax = Math.max(vmax, c.volume[i] || 0);
    if (vmax > 0) {
      for (let i = win.start; i < win.end; i++) {
        const isUp = c.close[i] >= c.open[i];
        const vh = ((c.volume[i] || 0) / vmax) * vb.h;
        ctx.fillStyle = isUp ? "rgba(239,83,80,.45)" : "rgba(38,166,154,.45)";
        ctx.fillRect(xAt(i) - cw / 2, vb.y0 + vb.h - vh, cw, vh);
      }
    }

    // ---- 底部全景缩略条：左右拖动窗格 ----
    {
      const ob = bands.overview;
      let lo = Infinity, hi = -Infinity;
      for (let i = 0; i < n; i++) { lo = Math.min(lo, c.low[i]); hi = Math.max(hi, c.high[i]); }
      if (!isFinite(lo)) { lo = 0; hi = 1; }
      const pad = (hi - lo) * 0.06 || 1;
      lo -= pad; hi += pad;
      const xAll = (i) => bands.plotX + (n === 1 ? bands.plotW / 2 : (i / (n - 1)) * bands.plotW);
      const yAll = (v) => ob.y0 + ob.h - ((v - lo) / (hi - lo)) * ob.h;
      // 全序列收盘价轮廓
      ctx.strokeStyle = "rgba(139,148,158,.55)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const x = xAll(i), y = yAll(c.close[i]);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
      // 可见窗口高亮 + 拖动把手
      const x0 = xAll(win.start);
      const x1 = xAll(Math.min(win.end - 1, n - 1));
      const ww = Math.max(3, x1 - x0);
      ctx.fillStyle = "rgba(79,140,255,.22)";
      ctx.fillRect(x0, ob.y0, ww, ob.h);
      ctx.strokeStyle = COLORS.accent;
      ctx.lineWidth = 1;
      ctx.strokeRect(x0 + 0.5, ob.y0 + 0.5, ww - 1, ob.h - 1);
      if (ww > 14) {  // 把手横线
        ctx.strokeStyle = "rgba(79,140,255,.9)";
        ctx.beginPath();
        const my = ob.y0 + ob.h / 2;
        ctx.moveTo(x0 + 5, my);
        ctx.lineTo(x0 + ww - 5, my);
        ctx.stroke();
      }
    }

    // ---- 副图指标窗格（MACD / KDJ / RSI 等）----
    (bands.paneBands || []).forEach(pb2 => {
      const pane = pb2.pane;
      let lo = Infinity, hi = -Infinity;
      pane.series.forEach(s => (s.values || []).forEach(v => {
        if (v !== null && v !== undefined && !isNaN(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      }));
      (pane.refs || []).forEach(r => { lo = Math.min(lo, r.v); hi = Math.max(hi, r.v); });
      if (!isFinite(lo)) { lo = 0; hi = 1; }
      const pad = (hi - lo) * 0.08 || 1;
      lo -= pad; hi += pad;
      const pyOf = (v) => pb2.y0 + pb2.h - ((v - lo) / (hi - lo)) * pb2.h;

      // 窗格标题
      ctx.fillStyle = COLORS.axis;
      ctx.font = "10px Segoe UI, Microsoft YaHei, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(pane.name || "", bands.plotX + 3, pb2.y0 + 9);
      // 参考线
      (pane.refs || []).forEach(r => {
        ctx.strokeStyle = r.color || COLORS.axis;
        ctx.setLineDash([3, 4]);
        ctx.beginPath();
        ctx.moveTo(bands.plotX, pyOf(r.v));
        ctx.lineTo(bands.plotX + bands.plotW, pyOf(r.v));
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillText(r.label || String(r.v), bands.plotX + 6, pyOf(r.v) - 4);
      });
      // 序列（线/柱）
      pane.series.forEach(s => {
        if (s.type === "bar") {
          const bw2 = bw * 0.55;
          for (let i = win.start; i < win.end; i++) {
            const v = s.values[i];
            if (v === null || v === undefined || isNaN(v)) continue;
            const x = xAt(i);
            const y0v = pyOf(0), y1v = pyOf(v);
            ctx.fillStyle = v >= 0 ? COLORS.up : COLORS.down;
            ctx.globalAlpha = 0.8;
            ctx.fillRect(x - bw2 / 2, Math.min(y0v, y1v), bw2, Math.max(1, Math.abs(y1v - y0v)));
            ctx.globalAlpha = 1;
          }
        } else {
          ctx.strokeStyle = s.color;
          ctx.lineWidth = s.width || 1.3;
          ctx.beginPath();
          let started = false;
          for (let i = win.start; i < win.end; i++) {
            const v = s.values[i];
            if (v === null || v === undefined || isNaN(v)) continue;
            const x = xAt(i), y = pyOf(v);
            if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
      });
    });

    // ---- 时间轴 ----
    ctx.fillStyle = COLORS.axis;
    ctx.font = "11px Segoe UI, Microsoft YaHei, sans-serif";
    ctx.textAlign = "center";
    const labelCount = Math.min(6, count);
    for (let k = 0; k < labelCount; k++) {
      const i = win.start + Math.round(k * (count - 1) / Math.max(1, labelCount - 1));
      if (i >= n) continue;
      const t = c.dates[i];
      const label = t.length > 10 ? t.slice(5, 16) : t.slice(2, 10);
      ctx.fillText(label, xAt(i), h - 8);
    }

    // ---- 十字线与提示框 ----
    if (this.hover >= win.start && this.hover < win.end) {
      const x = xAt(this.hover);
      ctx.strokeStyle = "rgba(139,148,158,.5)";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, pb.y0);
      ctx.lineTo(x, bands.volume.y0 + bands.volume.h);
      ctx.stroke();
      ctx.setLineDash([]);
      this._drawTooltip(ctx, w, h, x, win);
    }
  }

  _drawTooltip(ctx, w, h, x, win) {
    const c = this.candles;
    const i = this.hover;
    if (i < 0 || i >= c.dates.length) return;
    const isUp = c.close[i] >= c.open[i];
    const chg = c.open[i] ? (c.close[i] / c.open[i] - 1) * 100 : 0;
    const lines = [
      [c.dates[i], COLORS.text],
      [T("开 ") + fmtNum(c.open[i], 2) + "  " + T("高 ") + fmtNum(c.high[i], 2), COLORS.axis],
      [T("低 ") + fmtNum(c.low[i], 2) + "  " + T("收 ") + fmtNum(c.close[i], 2), COLORS.axis],
      [T("涨跌 ") + (chg >= 0 ? "+" : "") + chg.toFixed(2) + "%", chg >= 0 ? COLORS.up : COLORS.down],
      [T("量 ") + fmtNum(c.volume[i], 0), COLORS.axis],
    ];
    // 副图指标数值
    (this._bands().paneBands || []).forEach(pb2 => {
      pb2.pane.series.forEach(s => {
        const v = (s.values || [])[i];
        if (v === null || v === undefined) return;
        lines.push([(s.name || "") + "  " + (isNaN(v) ? "--" : Number(v).toFixed(s.decimals ?? 2)), s.color]);
      });
    });
    this.markers.forEach(m => {
      if (m.i === i) {
        const map = {
          buy: ["▲ " + T("买入（开多）"), COLORS.up],
          sell: ["▼ " + T("卖出（平多）"), COLORS.down],
          short: ["▼ " + T("融券卖出（开空）"), COLORS.down],
          cover: ["▲ " + T("买券还券（平空）"), COLORS.down],
        };
        const info = map[m.type];
        if (info) lines.push(info);
      }
    });
    const fs = 11.5;
    ctx.font = fs + "px Segoe UI, Microsoft YaHei, sans-serif";
    const tw = Math.max(...lines.map(l => ctx.measureText(l[0]).width)) + 18;
    const th = lines.length * (fs + 5) + 12;
    let tx = x + 12;
    if (tx + tw > w - 6) tx = x - tw - 12;
    const ty = 14;
    ctx.fillStyle = COLORS.tooltipBg;
    ctx.strokeStyle = COLORS.tooltipBorder;
    roundRect(ctx, tx, ty, tw, th, 6);
    ctx.fill();
    ctx.stroke();
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    lines.forEach((l, k) => {
      ctx.fillStyle = l[1];
      ctx.fillText(l[0], tx + 9, ty + 6 + k * (fs + 5));
    });
  }

  renderHover(e) {
    if (!this.candles || !this.candles.dates.length || this._drag) return;
    const rect = this.canvas.getBoundingClientRect();
    const bands = this._bands();
    const mx = e.clientX - rect.left;
    const win = this._window();
    if (mx < bands.plotX || mx > bands.plotX + bands.plotW) {
      if (this.hover !== -1) { this.hover = -1; this.render(); }
      return;
    }
    const bw = bands.plotW / win.count;
    const idx = win.start + Math.floor((mx - bands.plotX) / bw);
    if (idx !== this.hover) { this.hover = clamp(idx, 0, this.candles.dates.length - 1); this.render(); }
  }
}

/* ======================================================================
 * 折线图（净值曲线等）
 * ====================================================================== */
class LineChart {
  constructor(canvas) {
    this.canvas = canvas;
    this.dates = [];
    this.series = [];
    this.hover = -1;
    this._bind();
  }

  _bind() {
    this.canvas.addEventListener("mousemove", (e) => this.renderHover(e));
    this.canvas.addEventListener("mouseleave", () => {
      if (this.hover !== -1) { this.hover = -1; this.render(); }
    });
    // 触屏：点按/滑动查看数值
    this.canvas.addEventListener("touchstart", (e) => this.touchHover(e), { passive: true });
    this.canvas.addEventListener("touchmove", (e) => this.touchHover(e), { passive: true });
  }

  touchHover(e) {
    if (!this.dates.length || !e.touches.length) return;
    this.renderHover({ clientX: e.touches[0].clientX });
  }

  setData(dates, series) {
    this.dates = dates || [];
    this.series = series || [];
    this.hover = -1;
    this.render();
  }

  render() {
    const { w, h, ctx } = setupCanvas(this.canvas);
    const hasRight = this.series.some(s => s.axis === "right");
    const padL = hasRight ? 60 : 8, padR = 70, padT = 12, padB = 22;
    const plotW = w - padL - padR, plotH = h - padT - padB;
    if (!this.dates.length || !this.series.length) {
      ctx.fillStyle = COLORS.axis;
      ctx.font = "13px Segoe UI, Microsoft YaHei, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(T("暂无数据"), w / 2, h / 2);
      return;
    }
    const leftSeries = this.series.filter(s => s.axis !== "right");
    const rightSeries = this.series.filter(s => s.axis === "right");
    const rangeOf = (list) => {
      let lo = Infinity, hi = -Infinity;
      list.forEach(s => s.values.forEach(v => {
        if (v !== null && v !== undefined && !isNaN(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      }));
      if (!isFinite(lo)) { lo = 0; hi = 1; }
      const pad = (hi - lo) * 0.06 || 1;
      return { min: lo - pad, max: hi + pad };
    };
    const scaleL = niceScale(rangeOf(leftSeries).min, rangeOf(leftSeries).max, 4);
    drawGrid(ctx, padL, padT, plotW, plotH, scaleL,
      (v) => fmtNum(v, v >= 10000 ? 0 : 0), { alignRight: true });
    let scaleR = null;
    if (rightSeries.length) {
      const r = rangeOf(rightSeries);
      scaleR = niceScale(r.min, r.max, 4);
      drawGrid(ctx, padL, padT, plotW, plotH, scaleR,
        (v) => fmtNum(v, 1), { alignRight: false, dashed: true, color: "rgba(139,148,158,.25)" });
    }

    const n = this.dates.length;
    const xAt = (i) => padL + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
    const yL = (v) => padT + plotH - ((v - scaleL.min) / (scaleL.max - scaleL.min)) * plotH;
    const yR = (v) => scaleR ? padT + plotH - ((v - scaleR.min) / (scaleR.max - scaleR.min)) * plotH : null;

    this.series.forEach(s => {
      const yAt = s.axis === "right" ? yR : yL;
      ctx.strokeStyle = s.color;
      ctx.lineWidth = s.width || 1.6;
      ctx.beginPath();
      let started = false;
      s.values.forEach((v, i) => {
        if (v === null || v === undefined || isNaN(v)) return;
        const x = xAt(i), y = yAt(v);
        if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
      });
      ctx.stroke();
      if (s.fill) {
        ctx.save();
        ctx.lineTo(xAt(n - 1), padT + plotH);
        ctx.lineTo(xAt(0), padT + plotH);
        ctx.closePath();
        ctx.globalAlpha = 0.12;
        ctx.fillStyle = s.color;
        ctx.fill();
        ctx.restore();
      }
    });

    // 时间轴
    ctx.fillStyle = COLORS.axis;
    ctx.font = "11px Segoe UI, Microsoft YaHei, sans-serif";
    ctx.textAlign = "center";
    const labelCount = Math.min(6, n);
    for (let k = 0; k < labelCount; k++) {
      const i = Math.round(k * (n - 1) / Math.max(1, labelCount - 1));
      const t = this.dates[i];
      ctx.fillText(t.length > 10 ? t.slice(5, 16) : t.slice(2, 10), xAt(i), h - 8);
    }

    // 悬停
    if (this.hover >= 0 && this.hover < n) {
      const x = xAt(this.hover);
      ctx.strokeStyle = "rgba(139,148,158,.5)";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, padT + plotH);
      ctx.stroke();
      ctx.setLineDash([]);
      const lines = [[this.dates[this.hover], COLORS.text]];
      this.series.forEach(s => {
        lines.push([s.name + "  " + fmtNum(s.values[this.hover], s.decimals ?? 0), s.color]);
      });
      ctx.font = "11.5px Segoe UI, Microsoft YaHei, sans-serif";
      const tw = Math.max(...lines.map(l => ctx.measureText(l[0]).width)) + 18;
      const th = lines.length * 16.5 + 12;
      let tx = x + 12;
      if (tx + tw > w - 6) tx = x - tw - 12;
      ctx.fillStyle = COLORS.tooltipBg;
      ctx.strokeStyle = COLORS.tooltipBorder;
      roundRect(ctx, tx, 14, tw, th, 6);
      ctx.fill();
      ctx.stroke();
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      lines.forEach((l, k) => {
        ctx.fillStyle = l[1];
        ctx.fillText(l[0], tx + 9, 20 + k * 16.5);
      });
    }
  }

  renderHover(e) {
    if (!this.dates.length) return;
    const rect = this.canvas.getBoundingClientRect();
    const hasRight = this.series.some(s => s.axis === "right");
    const padL = hasRight ? 60 : 8, padR = 70;
    const plotW = rect.width - padL - padR;
    const mx = e.clientX - rect.left - padL;
    const n = this.dates.length;
    const idx = clamp(Math.round((mx / plotW) * (n - 1)), 0, n - 1);
    if (idx !== this.hover) { this.hover = idx; this.render(); }
  }
}
