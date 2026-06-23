const state = {
  reports: [],
  activeReport: null,
  activeSection: "complete",
  liveQuant: null,
  fundamentalSnapshot: null,
  chartRange: 30,
  chartHoverIndex: null,
  hotspotData: null,
  hotspotView: "stocks",
  hotspotJobId: null,
  hotspotAvailableDates: [],
  hotspotScannedDates: [],
  hotspotSelectedDate: "",
  hotspotCalendarMonth: null,
  singleWorkspaceInitialized: false,
  hotspotWorkspaceInitialized: false,
};

const $ = (id) => document.getElementById(id);

function setStatus(text, kind = "neutral") {
  const node = $("statusLine");
  const icon = kind === "error" ? "i-alert" : "i-activity";
  node.innerHTML = `<svg><use href="#${icon}" /></svg><span>${escapeHtml(text)}</span>`;
  node.dataset.kind = kind;
}

function badgeClass(value) {
  const v = String(value || "").toUpperCase();
  if (v.includes("BUY") || v.includes("买")) return "badge buy";
  if (v.includes("SELL") || v.includes("卖") || v.includes("RISK")) return "badge sell";
  if (v.includes("HOLD") || v.includes("WATCH") || v.includes("观望")) return "badge hold";
  if (v.includes("ERROR") || v.includes("UNAVAILABLE")) return "badge error";
  return "badge neutral";
}

function displayQuantSignal(value) {
  const labels = {
    ACTIVE_BUY_OR_HOLD: "持有 / 监控退场",
    ACTIVE_HOLD_MONITOR: "持有 / 监控退场",
    PENDING_ENTRY: "等待下一交易日入场",
    WAIT_FOR_ENTRY_PRICE: "等待进入建议买入区间",
    ENTRY_BLOCKED_LIMIT_UP: "涨停附近无法入场",
    FUNDAMENTAL_REVIEW_REQUIRED: "基本面复核 / 暂停入场",
    SELL_TAKE_PROFIT: "止盈",
    REDUCE_OR_EXIT: "减仓 / 退出",
    NO_BUY_SIGNAL: "无买入信号",
    DATA_UNAVAILABLE: "数据不可用",
    EXPIRED: "信号过期",
  };
  return labels[String(value || "").toUpperCase()] || value || "-";
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function renderTable(lines, startIndex) {
  const rows = [];
  let i = startIndex;
  while (i < lines.length && lines[i].trim().startsWith("|")) {
    const raw = lines[i].trim();
    if (!/^\|\s*-+/.test(raw)) {
      rows.push(raw.slice(1, -1).split("|").map((cell) => inlineMarkdown(cell.trim())));
    }
    i += 1;
  }
  if (!rows.length) return { html: "", next: i };
  const head = rows.shift();
  const headHtml = `<tr>${head.map((cell) => `<th>${cell}</th>`).join("")}</tr>`;
  const bodyHtml = rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("");
  return { html: `<table><thead>${headHtml}</thead><tbody>${bodyHtml}</tbody></table>`, next: i };
}

function renderMarkdown(markdown) {
  if (!markdown || !markdown.trim()) {
    return '<div class="empty-state">当前报告没有这一部分内容</div>';
  }
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let listOpen = false;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) {
      if (listOpen) {
        out.push("</ul>");
        listOpen = false;
      }
      continue;
    }
    if (trimmed.startsWith("|")) {
      if (listOpen) {
        out.push("</ul>");
        listOpen = false;
      }
      const table = renderTable(lines, i);
      out.push(table.html);
      i = table.next - 1;
      continue;
    }
    if (/^#{1,3}\s+/.test(trimmed)) {
      if (listOpen) {
        out.push("</ul>");
        listOpen = false;
      }
      const level = trimmed.match(/^#+/)[0].length;
      out.push(`<h${level}>${inlineMarkdown(trimmed.replace(/^#{1,3}\s+/, ""))}</h${level}>`);
      continue;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      if (!listOpen) {
        out.push("<ul>");
        listOpen = true;
      }
      out.push(`<li>${inlineMarkdown(trimmed.replace(/^[-*]\s+/, ""))}</li>`);
      continue;
    }
    if (listOpen) {
      out.push("</ul>");
      listOpen = false;
    }
    out.push(`<p>${inlineMarkdown(trimmed)}</p>`);
  }
  if (listOpen) out.push("</ul>");
  return out.join("");
}

function parseNumber(value) {
  if (!value) return null;
  const text = String(value).replaceAll(",", "");
  const match = text.match(/-?\d+(?:\.\d+)?/);
  if (!match) return null;
  return Number(match[0]);
}

function parsePercent(value) {
  const n = parseNumber(value);
  return n == null ? null : n;
}

function formatPercentText(value, signed = false) {
  const number = parsePercent(value);
  if (number == null) return "-";
  return `${signed && number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function formatMoney(value) {
  if (value == null || !Number.isFinite(Number(value))) return "-";
  const number = Number(value);
  const absolute = Math.abs(number);
  if (absolute >= 100_000_000) return `${(number / 100_000_000).toFixed(2)} 亿`;
  if (absolute >= 10_000) return `${(number / 10_000).toFixed(1)} 万`;
  return number.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function formatMetric(value, suffix = "", digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return "-";
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function formatChange(value) {
  if (value == null || !Number.isFinite(Number(value))) return "同比 -";
  const number = Number(value);
  return `同比 ${number >= 0 ? "+" : ""}${number.toFixed(1)}%`;
}

function periodLabel(value) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  const quarter = Math.ceil((date.getMonth() + 1) / 3);
  return `${String(date.getFullYear()).slice(2)}Q${quarter}`;
}

function resizeCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(320, Math.floor(rect.width * dpr));
  canvas.height = Math.max(280, Math.floor(rect.height * dpr));
  return dpr;
}

let flowChartModel = null;

function formatFlowAxis(value) {
  const abs = Math.abs(value);
  if (abs >= 10000) return `${value < 0 ? "-" : ""}${(abs / 10000).toFixed(1)}亿`;
  if (abs >= 1000) return `${value < 0 ? "-" : ""}${(abs / 1000).toFixed(1)}千万`;
  return `${Math.round(value)}万`;
}

function updateChartReadout(row) {
  $("chartReadoutDate").textContent = row?.date ? `交易日 ${row.date}` : "交易日 --";
  $("chartReadoutClose").textContent = row?.close == null ? "--" : `¥${row.close.toFixed(2)}`;
  $("chartReadoutFlow").textContent = row?.net == null
    ? "--"
    : `${row.net >= 0 ? "+" : ""}${row.net.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 万元`;
  $("chartReadoutFlow").className = row?.net == null ? "" : row.net >= 0 ? "positive" : "negative";
}

function visibleFlowRows(rows) {
  const parsed = (rows || [])
    .map((row) => ({
      date: row.date,
      close: parseNumber(row.close),
      net: parseNumber(row.netInflow),
      ratio: parsePercent(row.inflowRatio),
      signal: row.signal,
    }))
    .filter((row) => row.close != null || row.net != null);
  return state.chartRange > 0 ? parsed.slice(-state.chartRange) : parsed;
}

function setChartRange(days) {
  state.chartRange = days;
  state.chartHoverIndex = null;
  document.querySelectorAll("#chartRangeControls button").forEach((button) => {
    const active = Number(button.dataset.days) === days;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const quant = state.liveQuant?.summary || state.activeReport?.quantSummary || {};
  drawChart(quant.rows || []);
}

function drawChart(rows) {
  const canvas = $("flowChart");
  const dpr = resizeCanvas(canvas);
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.scale(dpr, dpr);
  const w = width / dpr;
  const h = height / dpr;
  ctx.fillStyle = "#101319";
  ctx.fillRect(0, 0, w, h);

  const left = 76;
  const right = 64;
  const top = 24;
  const bottom = 50;
  const plotW = w - left - right;
  const plotH = h - top - bottom;
  const parsed = visibleFlowRows(rows);

  if (!parsed.length) {
    ctx.fillStyle = "#848e9c";
    ctx.font = "13px system-ui";
    ctx.fillText("暂无量化序列，生成实时策略后会显示资金异动图。", left, top + 48);
    $("chartBadge").className = "badge neutral";
    $("chartBadge").textContent = "NO DATA";
    updateChartReadout(null);
    flowChartModel = null;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    return;
  }

  const maxAbsNet = Math.max(...parsed.map((row) => Math.abs(row.net || 0)), 1) * 1.12;
  const closes = parsed.map((row) => row.close).filter((n) => n != null);
  const rawMinClose = Math.min(...closes);
  const rawMaxClose = Math.max(...closes);
  const closePadding = Math.max((rawMaxClose - rawMinClose) * 0.10, rawMaxClose * 0.01, 0.02);
  const minClose = rawMinClose - closePadding;
  const maxClose = rawMaxClose + closePadding;
  const closeRange = maxClose - minClose;
  const step = plotW / parsed.length;
  const barW = Math.max(2, Math.min(18, step * 0.62));
  const zeroY = top + plotH / 2;
  const xAt = (index) => left + step * (index + 0.5);
  const netY = (value) => zeroY - ((value || 0) / maxAbsNet) * (plotH / 2);
  const closeY = (value) => top + ((maxClose - value) / closeRange) * plotH;

  ctx.font = "10px Arial, Microsoft YaHei, sans-serif";
  ctx.lineWidth = 1;
  for (let index = 0; index <= 4; index += 1) {
    const y = top + (plotH * index) / 4;
    const netTick = maxAbsNet - (index * maxAbsNet) / 2;
    const priceTick = maxClose - (index * closeRange) / 4;
    ctx.strokeStyle = index === 2 ? "rgba(234,236,239,0.34)" : "rgba(132,142,156,0.16)";
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotW, y);
    ctx.stroke();
    ctx.fillStyle = "#848e9c";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.fillText(formatFlowAxis(netTick), left - 10, y);
    ctx.textAlign = "left";
    ctx.fillText(`¥${priceTick.toFixed(2)}`, left + plotW + 10, y);
  }

  parsed.forEach((row, index) => {
    const x = xAt(index);
    const y = netY(row.net);
    ctx.fillStyle = row.net >= 0 ? "rgba(246,70,93,0.78)" : "rgba(14,203,129,0.76)";
    ctx.fillRect(x - barW / 2, Math.min(y, zeroY), barW, Math.max(1.5, Math.abs(zeroY - y)));
    if (String(row.signal || "").toUpperCase().includes("BUY")) {
      ctx.fillStyle = "#fcd535";
      ctx.beginPath();
      ctx.moveTo(x, top + 2);
      ctx.lineTo(x - 5, top + 10);
      ctx.lineTo(x + 5, top + 10);
      ctx.closePath();
      ctx.fill();
    }
  });

  ctx.strokeStyle = "#fcd535";
  ctx.lineWidth = 2.2;
  ctx.beginPath();
  parsed.forEach((row, index) => {
    if (row.close == null) return;
    const x = xAt(index);
    const y = closeY(row.close);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  const tickCount = Math.min(6, parsed.length);
  const tickIndices = new Set();
  for (let index = 0; index < tickCount; index += 1) {
    tickIndices.add(Math.round((parsed.length - 1) * index / Math.max(tickCount - 1, 1)));
  }
  ctx.fillStyle = "#848e9c";
  ctx.font = "10px Arial, Microsoft YaHei, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  tickIndices.forEach((index) => {
    ctx.fillText(parsed[index].date.slice(5), xAt(index), top + plotH + 13);
  });

  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.beginPath();
  ctx.moveTo(left, top);
  ctx.lineTo(left, top + plotH);
  ctx.lineTo(left + plotW, top + plotH);
  ctx.stroke();

  const selectedIndex = state.chartHoverIndex == null
    ? parsed.length - 1
    : Math.max(0, Math.min(state.chartHoverIndex, parsed.length - 1));
  const selected = parsed[selectedIndex];
  const selectedX = xAt(selectedIndex);
  ctx.strokeStyle = "rgba(234,236,239,0.48)";
  ctx.setLineDash([3, 4]);
  ctx.beginPath();
  ctx.moveTo(selectedX, top);
  ctx.lineTo(selectedX, top + plotH);
  ctx.stroke();
  ctx.setLineDash([]);
  if (selected.close != null) {
    ctx.fillStyle = "#fcd535";
    ctx.beginPath();
    ctx.arc(selectedX, closeY(selected.close), 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#101319";
    ctx.stroke();
  }
  updateChartReadout(selected);

  const latestFlow = parsed.at(-1)?.net;
  $("chartBadge").className = latestFlow == null ? "badge watch" : latestFlow >= 0 ? "badge buy" : "badge sell";
  $("chartBadge").textContent = latestFlow == null ? "WATCH" : latestFlow >= 0 ? "LATEST INFLOW" : "LATEST OUTFLOW";
  flowChartModel = { left, plotW, step, count: parsed.length };
  ctx.setTransform(1, 0, 0, 1, 0, 0);
}

function drawFundamentalChart(trends) {
  const canvas = $("fundamentalChart");
  const dpr = resizeCanvas(canvas);
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.scale(dpr, dpr);
  const w = width / dpr;
  const h = height / dpr;
  ctx.fillStyle = "#101319";
  ctx.fillRect(0, 0, w, h);

  const rows = (trends || []).filter((row) => row.revenue != null || row.netProfit != null || row.operatingCashFlow != null);
  const left = 58;
  const right = 58;
  const top = 38;
  const bottom = 42;
  const plotW = w - left - right;
  const plotH = h - top - bottom;

  ctx.strokeStyle = "rgba(132,142,156,0.16)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const y = top + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotW, y);
    ctx.stroke();
  }

  if (!rows.length) {
    ctx.fillStyle = "#848e9c";
    ctx.font = "13px system-ui";
    ctx.fillText("暂无可绘制的财务趋势数据。", left, top + 48);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    return;
  }

  const revenues = rows.map((row) => Number(row.revenue) || 0);
  const profits = rows.flatMap((row) => [Number(row.netProfit) || 0, Number(row.operatingCashFlow) || 0]);
  const revenueMax = Math.max(...revenues.map(Math.abs), 1);
  const profitAbs = Math.max(...profits.map(Math.abs), 1);
  const profitMin = -profitAbs;
  const profitMax = profitAbs;
  const slot = plotW / rows.length;
  const barW = Math.max(8, Math.min(34, slot * 0.42));

  ctx.fillStyle = "rgba(240,185,11,0.62)";
  rows.forEach((row, index) => {
    const revenue = Number(row.revenue) || 0;
    const x = left + slot * index + (slot - barW) / 2;
    const barH = (Math.abs(revenue) / revenueMax) * plotH * 0.88;
    ctx.fillRect(x, top + plotH - barH, barW, Math.max(2, barH));
    ctx.fillStyle = "#5e6673";
    ctx.font = "10px system-ui";
    ctx.fillText(periodLabel(row.period), x - 2, h - 16);
    ctx.fillStyle = "rgba(240,185,11,0.62)";
  });

  const drawLine = (field, color) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    rows.forEach((row, index) => {
      const value = Number(row[field]);
      if (!Number.isFinite(value)) return;
      const x = left + slot * index + slot / 2;
      const y = top + plotH - ((value - profitMin) / (profitMax - profitMin)) * plotH;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };
  drawLine("netProfit", "#0ecb81");
  drawLine("operatingCashFlow", "#4a8cff");

  ctx.fillStyle = "#fcd535";
  ctx.fillRect(left, 13, 12, 7);
  ctx.fillStyle = "#848e9c";
  ctx.font = "11px system-ui";
  ctx.fillText("累计营收", left + 18, 21);
  ctx.strokeStyle = "#0ecb81";
  ctx.beginPath();
  ctx.moveTo(left + 92, 17);
  ctx.lineTo(left + 106, 17);
  ctx.stroke();
  ctx.fillText("归母净利润", left + 111, 21);
  ctx.strokeStyle = "#4a8cff";
  ctx.beginPath();
  ctx.moveTo(left + 191, 17);
  ctx.lineTo(left + 205, 17);
  ctx.stroke();
  ctx.fillText("经营现金流", left + 210, 21);

  ctx.fillStyle = "#5e6673";
  ctx.font = "10px system-ui";
  ctx.fillText(`${(revenueMax / 100_000_000).toFixed(1)}亿`, 8, top + 5);
  ctx.fillText(`${(profitMax / 100_000_000).toFixed(1)}亿`, w - right + 8, top + 5);
  ctx.fillText(`${(profitMin / 100_000_000).toFixed(1)}亿`, w - right + 8, top + plotH);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
}

function evidenceMeta(grade) {
  const key = String(grade || "INSUFFICIENT_SAMPLE").toUpperCase();
  const map = {
    PROMISING_IN_SAMPLE: { label: "样本内积极", className: "positive" },
    POSITIVE_BUT_UNPROVEN: { label: "正收益但未验证", className: "watch" },
    NOT_VALIDATED: { label: "暂未验证", className: "negative" },
    INSUFFICIENT_SAMPLE: { label: "样本不足", className: "neutral" },
  };
  return map[key] || { label: key.replaceAll("_", " "), className: "neutral" };
}

function calculateEvidenceScore(quant) {
  const trades = parseNumber(quant.completedTrades) || 0;
  const winRate = parsePercent(quant.winRate);
  const totalReturn = parsePercent(quant.totalReturn);
  const excess = parsePercent(quant.excessReturn);
  const drawdown = parsePercent(quant.maxDrawdown);
  const profitFactor = parseNumber(quant.profitFactor);
  let score = Math.min(trades / 8, 1) * 32;
  if (winRate != null) score += Math.max(0, Math.min(winRate / 65, 1)) * 18;
  if (totalReturn != null) score += Math.max(0, Math.min((totalReturn + 5) / 30, 1)) * 18;
  if (excess != null) score += Math.max(0, Math.min((excess + 5) / 20, 1)) * 14;
  if (drawdown != null) score += Math.max(0, Math.min((20 + drawdown) / 20, 1)) * 10;
  if (profitFactor != null) score += Math.max(0, Math.min(profitFactor / 2, 1)) * 8;
  if (trades < 5) score = Math.min(score, 44);
  return Math.max(0, Math.min(100, Math.round(score)));
}

function drawBacktestChart(trades) {
  const canvas = $("backtestChart");
  const dpr = resizeCanvas(canvas);
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.scale(dpr, dpr);
  const w = width / dpr;
  const h = height / dpr;
  ctx.fillStyle = "#101319";
  ctx.fillRect(0, 0, w, h);

  const left = 54;
  const right = 22;
  const top = 24;
  const bottom = 38;
  const plotW = w - left - right;
  const plotH = h - top - bottom;
  ctx.strokeStyle = "rgba(132,142,156,0.16)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const y = top + plotH * i / 4;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotW, y);
    ctx.stroke();
  }

  const points = [{ equity: 100, label: "START" }];
  let equity = 100;
  (trades || []).forEach((trade, index) => {
    const value = parsePercent(trade.return);
    if (value == null) return;
    equity *= 1 + value / 100;
    points.push({ equity, label: trade.exitDate || `T${index + 1}` });
  });

  if (points.length === 1) {
    ctx.fillStyle = "#848e9c";
    ctx.font = "12px Arial";
    ctx.fillText("暂无已完成交易，权益曲线需要至少一笔退出记录。", left, top + 48);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    return;
  }

  const values = points.map((point) => point.equity);
  const minValue = Math.min(...values, 100) * 0.98;
  const maxValue = Math.max(...values, 100) * 1.02;
  const range = Math.max(maxValue - minValue, 1);
  const coords = points.map((point, index) => ({
    ...point,
    x: left + plotW * index / Math.max(points.length - 1, 1),
    y: top + plotH - (point.equity - minValue) / range * plotH,
  }));

  const gradient = ctx.createLinearGradient(0, top, 0, top + plotH);
  gradient.addColorStop(0, "rgba(252,213,53,0.24)");
  gradient.addColorStop(1, "rgba(252,213,53,0)");
  ctx.beginPath();
  ctx.moveTo(coords[0].x, top + plotH);
  coords.forEach((point) => ctx.lineTo(point.x, point.y));
  ctx.lineTo(coords[coords.length - 1].x, top + plotH);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  ctx.beginPath();
  coords.forEach((point, index) => index === 0 ? ctx.moveTo(point.x, point.y) : ctx.lineTo(point.x, point.y));
  ctx.strokeStyle = "#fcd535";
  ctx.lineWidth = 2.2;
  ctx.stroke();
  coords.forEach((point) => {
    ctx.beginPath();
    ctx.arc(point.x, point.y, 3.2, 0, Math.PI * 2);
    ctx.fillStyle = point.equity >= 100 ? "#f6465d" : "#0ecb81";
    ctx.fill();
  });

  ctx.fillStyle = "#848e9c";
  ctx.font = "10px Arial";
  ctx.fillText(maxValue.toFixed(1), 8, top + 4);
  ctx.fillText(minValue.toFixed(1), 8, top + plotH);
  coords.forEach((point, index) => {
    if (index === 0 || index === coords.length - 1 || index % Math.ceil(coords.length / 5) === 0) {
      ctx.fillText(point.label.slice(5) || point.label, Math.max(left, point.x - 15), h - 14);
    }
  });
  ctx.setTransform(1, 0, 0, 1, 0, 0);
}

function updateBacktest(quant) {
  const trades = quant.backtestTrades || [];
  const tradeCount = parseNumber(quant.completedTrades) || trades.length || 0;
  const score = calculateEvidenceScore(quant);
  const meta = evidenceMeta(quant.evidenceGrade);
  const grade = $("backtestGrade");
  grade.className = `evidence-grade ${meta.className}`;
  grade.textContent = meta.label.toUpperCase();
  $("evidenceScore").textContent = String(score);
  $("evidenceLabel").textContent = meta.label;
  $("evidenceGauge").style.setProperty("--score", `${score * 0.9}deg`);

  $("btTrades").textContent = String(tradeCount);
  $("btWinRate").textContent = formatPercentText(quant.winRate);
  $("btDrawdown").textContent = formatPercentText(quant.maxDrawdown);
  $("btProfitFactor").textContent = parseNumber(quant.profitFactor)?.toFixed(2) || "-";
  $("btHolding").textContent = parseNumber(quant.averageHoldingDays) == null ? "-" : `${parseNumber(quant.averageHoldingDays).toFixed(1)} 天`;
  $("backtestReturn").textContent = formatPercentText(quant.totalReturn, true);
  $("benchmarkReturn").textContent = formatPercentText(quant.benchmarkReturn, true);
  $("excessReturn").textContent = formatPercentText(quant.excessReturn, true);

  const strategyReturn = parsePercent(quant.totalReturn);
  const benchmark = parsePercent(quant.benchmarkReturn);
  const scale = Math.max(Math.abs(strategyReturn || 0), Math.abs(benchmark || 0), 1);
  const setBar = (id, value, positiveColor) => {
    const node = $(id);
    node.style.width = `${Math.min(Math.abs(value || 0) / scale * 100, 100)}%`;
    node.style.background = value != null && value < 0 ? "#0ecb81" : positiveColor;
  };
  setBar("strategyReturnBar", strategyReturn, "#fcd535");
  setBar("benchmarkReturnBar", benchmark, "#4a8cff");

  $("backtestTradeBody").innerHTML = trades.length
    ? trades.map((trade) => {
      const value = parsePercent(trade.return);
      const valueClass = value == null ? "" : value >= 0 ? "positive" : "negative";
      return `<tr>
        <td>${escapeHtml(trade.signalDate)}</td><td>${escapeHtml(trade.entryDate)}</td><td>${escapeHtml(trade.exitDate)}</td>
        <td>${escapeHtml(trade.entryPrice)}</td><td>${escapeHtml(trade.exitPrice)}</td>
        <td class="${valueClass}">${escapeHtml(trade.return)}</td><td>${escapeHtml(trade.holdingDays)} 天</td>
        <td>${escapeHtml(displayQuantSignal(trade.status))}</td>
      </tr>`;
    }).join("")
    : '<tr><td colspan="8" class="table-empty">暂无已完成交易；不能据此证明策略可行</td></tr>';
  $("healthBacktest").textContent = tradeCount >= 5 ? meta.label : `样本不足（${tradeCount}/5）`;
  drawBacktestChart(trades);
}

function updateHero(report, quant) {
  const rows = quant.rows || [];
  const closes = rows.map((row) => parseNumber(row.close)).filter((value) => value != null);
  const latest = parseNumber(quant.latestClose) ?? closes.at(-1);
  const previous = closes.length > 1 ? closes.at(-2) : null;
  const change = latest != null && previous ? (latest / previous - 1) * 100 : null;
  $("heroTicker").textContent = report?.ticker || "A-SHARE";
  $("heroPrice").textContent = latest == null ? "--" : `¥${latest.toFixed(2)}`;
  const changeNode = $("heroChange");
  changeNode.className = `price-change ${change == null ? "neutral" : change >= 0 ? "positive" : "negative"}`;
  changeNode.textContent = change == null ? "等待最新收盘" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}% 最近交易日`;
}

function updateFundamentalView(snapshot, loading = false) {
  const metrics = snapshot?.metrics || {};
  const company = snapshot?.company || {};
  $("fundRevenue").textContent = formatMoney(metrics.revenue);
  $("fundRevenueYoy").textContent = formatChange(metrics.revenueYoY);
  $("fundNetProfit").textContent = formatMoney(metrics.netProfit);
  $("fundProfitYoy").textContent = formatChange(metrics.netProfitYoY);
  $("fundReturns").textContent = `${formatMetric(metrics.roe, "%")} / ${formatMetric(metrics.grossMargin, "%")}`;
  $("fundNetMargin").textContent = `净利率 ${formatMetric(metrics.netMargin, "%")}`;
  $("fundCashFlow").textContent = formatMoney(metrics.operatingCashFlow);
  const cashQuality = metrics.operatingCashFlow != null && metrics.netProfit != null
    ? metrics.operatingCashFlow >= metrics.netProfit ? "现金流覆盖利润" : "现金流低于利润"
    : "现金质量 -";
  $("fundCashQuality").textContent = cashQuality;
  $("fundDebtRatio").textContent = formatMetric(metrics.debtRatio, "%");
  $("fundCurrentRatio").textContent = `流动比率 ${formatMetric(metrics.currentRatio, "", 2)}`;
  $("fundValuation").textContent = `${formatMetric(metrics.peTtm, "x")} / ${formatMetric(metrics.pb, "x")}`;
  $("fundValuationDate").textContent = `估值日 ${snapshot?.valuationDate || "-"}`;
  $("fundamentalSubtitle").textContent = snapshot
    ? `${company.name || snapshot.ticker} · ${company.industry || "行业未标注"} · 报告期 ${snapshot.latestPeriod || "-"}`
    : "Tushare 财务报表与每日估值";
  $("healthFinancials").textContent = loading
    ? "加载中"
    : !snapshot ? "不可用" : snapshot.errors?.length ? "部分可用" : "完整";

  const badge = $("fundamentalBadge");
  if (loading) {
    badge.className = "badge neutral";
    badge.textContent = "LOADING";
  } else if (!snapshot) {
    badge.className = "badge error";
    badge.textContent = "NO DATA";
  } else if (snapshot.errors?.length) {
    badge.className = "badge watch";
    badge.textContent = "PARTIAL";
  } else {
    badge.className = "badge signal";
    badge.textContent = snapshot.cached ? "CACHED" : "TUSHARE";
  }

  const summary = snapshot?.summary || [];
  $("fundamentalSummary").innerHTML = summary.length
    ? `<h3>财务摘要</h3>${summary.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}`
    : `<div class="empty-state">${loading ? "正在读取财务数据" : "暂无财务摘要"}</div>`;
  drawFundamentalChart(snapshot?.trends || []);
}

function sectionText(report, section) {
  if (!report) return "";
  if (section === "quant" && state.liveQuant?.markdown) return state.liveQuant.markdown;
  return report.sections?.[section] || "";
}

function updateTabs() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.section === state.activeSection);
  });
  $("reportContent").innerHTML = renderMarkdown(sectionText(state.activeReport, state.activeSection));
}

function digestFromSections(report) {
  const sections = report?.sections || {};
  const candidates = [
    ["新闻政策", sections.news],
    ["基本面", sections.fundamentals],
    ["情绪", sections.sentiment],
  ];
  return candidates.map(([label, text]) => {
    const cleaned = String(text || "")
      .replace(/[#*_>`|]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return { label, text: cleaned || "暂无内容" };
  });
}

function updateDashboard(report) {
  const quant = state.liveQuant?.summary || report?.quantSummary || {};
  const decision = report?.signal || "UNKNOWN";
  $("pageTitle").textContent = report ? `${report.ticker} 策略监控` : "A股策略监控台";
  $("analysisDate").textContent = report?.analysisDate || "-";
  $("decisionBadge").className = badgeClass(decision);
  $("decisionBadge").textContent = decision;
  $("tickerInput").value = report?.ticker || $("tickerInput").value || "";
  $("dateInput").value = report?.analysisDate || $("dateInput").value || new Date().toISOString().slice(0, 10);

  $("metricQuantSignal").textContent = displayQuantSignal(quant.signal);
  $("metricReason").textContent = quant.reason || "暂无量化摘要";
  const exitSignal = ["REDUCE_OR_EXIT", "SELL_TAKE_PROFIT", "EXPIRED"].includes(String(quant.signal || "").toUpperCase());
  $("metricDay0").textContent = exitSignal ? "暂停入场" : quant.entryZone || "-";
  $("metricNetInflow").textContent = exitSignal
    ? `当前为退场信号${quant.entryZone ? ` / 估值观察区 ${quant.entryZone}` : ""}`
    : [
      quant.entryPrice ? `T+1参考 ${quant.entryPrice}` : "",
      quant.day0 ? `Day 0 ${quant.day0}` : "",
    ].filter(Boolean).join(" / ") || "等待入场评估";
  $("metricLevels").textContent = quant.suggestedExit || quant.currentExit || quant.riskExit || "-";
  $("metricLatestClose").textContent = [
    quant.takeProfit ? `止盈 ${quant.takeProfit}` : "",
    quant.riskExit ? `初始风控 ${quant.riskExit}` : "",
  ].filter(Boolean).join(" / ") || `最新收盘 ${quant.latestClose || "-"}`;
  $("metricDecision").textContent = decision;
  $("metricModified").textContent = report?.modified ? `更新 ${report.modified}` : "-";
  const latestNetInflow = quant.latestNetInflow || quant.netInflow || "-";
  const latestNetValue = parseNumber(latestNetInflow);
  const latestFlowLabel = latestNetValue != null && latestNetValue < 0 ? "最近3日净流出" : "最近3日净流入";
  $("metricFlowRatio").textContent = quant.latestInflowRatio || quant.inflowRatio || "-";
  $("metricNetAmount").textContent = `${quant.latestFlowDate ? `截至 ${quant.latestFlowDate} ` : ""}${latestFlowLabel} ${latestNetInflow}`;

  $("strategyAction").textContent = displayQuantSignal(quant.signal);
  $("strategyActionReason").textContent = quant.reason || "暂无策略判断";
  $("strategyEntry").textContent = exitSignal ? "暂停入场" : quant.entryPrice || quant.entryZone || "-";
  $("strategyTarget").textContent = quant.takeProfit || "-";
  $("strategyExit").textContent = quant.suggestedExit || quant.currentExit || quant.riskExit || "-";

  $("sourceReport").textContent = report ? "已加载" : "-";
  $("sourceQuant").textContent = state.liveQuant ? "实时生成" : report?.sections?.quant ? "报告内" : "未生成";
  $("sourceFundamentals").textContent = state.fundamentalSnapshot ? "Tushare" : "未加载";
  $("sourceLog").textContent = report?.sections?.fetchLog ? "已记录" : "无";
  $("healthReport").textContent = report?.sections?.complete ? "完整" : "未加载";
  $("healthQuant").textContent = state.liveQuant ? "实时计算" : report?.sections?.quant ? "报告快照" : "未生成";

  $("policyDigest").innerHTML = digestFromSections(report)
    .map((item) => `<div class="digest-item"><b>${escapeHtml(item.label)}</b><span>${escapeHtml(item.text)}</span></div>`)
    .join("");

  drawChart(quant.rows || []);
  updateHero(report, quant);
  updateBacktest(quant);
  updateFundamentalView(state.fundamentalSnapshot);
  updateTabs();
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  }
  return data;
}

function hotspotPercent(value, signed = false) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${signed && number > 0 ? "+" : ""}${(number * 100).toFixed(2)}%`;
}

function hotspotChange(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function hotspotClass(value) {
  const number = Number(value);
  return !Number.isFinite(number) || number === 0 ? "" : number > 0 ? "hotspot-positive" : "hotspot-negative";
}

function setHotspotJob(text, kind = "neutral") {
  const node = $("hotspotJobStatus");
  node.dataset.kind = kind;
  node.innerHTML = `<span class="pulse"></span><span>${escapeHtml(text)}</span>`;
}

function renderHotspotSectors(sectors) {
  $("hotspotSectorBody").innerHTML = sectors?.length
    ? sectors.map((sector, index) => `<tr>
        <td>${index + 1}</td><td>${escapeHtml(sector.sector_name || "未分类")}</td>
        <td class="hotspot-score">${Number(sector.sector_score || 0).toFixed(1)}</td>
        <td>${Number(sector.triggered_stock_count || 0)}/${Number(sector.stock_count || 0)}</td>
        <td class="${hotspotClass(sector.avg_net_flow_ratio)}">${hotspotPercent(sector.avg_net_flow_ratio, true)}</td>
        <td>${Number(sector.avg_amount_ratio_20 || 0).toFixed(2)}x</td>
      </tr>`).join("")
    : '<tr><td colspan="6" class="table-empty">暂无板块结果</td></tr>';
}

function renderHotspotStocks() {
  const data = state.hotspotData || {};
  const rows = [...(data[state.hotspotView] || [])];
  const sortKey = $("hotspotSort").value;
  rows.sort((left, right) => Number(right[sortKey] ?? -Infinity) - Number(left[sortKey] ?? -Infinity));
  $("hotspotStockBody").innerHTML = rows.length
    ? rows.map((stock) => `<tr>
        <td><span class="ticker-name">${escapeHtml(stock.name || stock.ts_code)}</span><span class="ticker-code">${escapeHtml(stock.ts_code)}</span></td>
        <td>${escapeHtml(stock.sector_level_1 || "未分类")}</td>
        <td class="hotspot-score">${Number(stock.stock_score || 0).toFixed(1)}</td>
        <td class="${hotspotClass(stock.pct_chg)}">${hotspotChange(stock.pct_chg)}</td>
        <td class="${hotspotClass(stock.net_flow_ratio)}">${hotspotPercent(stock.net_flow_ratio, true)}</td>
        <td class="${hotspotClass(stock.big_elg_flow_ratio)}">${hotspotPercent(stock.big_elg_flow_ratio, true)}</td>
        <td class="${hotspotClass(stock.block_vwap_premium)}">${hotspotPercent(stock.block_vwap_premium, true)}</td>
        <td>${Number(stock.amount_ratio_20 || 0).toFixed(2)}x</td>
        <td><button class="hotspot-analyze" type="button" data-ticker="${escapeHtml(stock.ts_code)}">单股分析</button></td>
      </tr>`).join("")
    : '<tr><td colspan="9" class="table-empty">当前榜单没有符合条件的股票</td></tr>';
}

function renderHotspot(data) {
  state.hotspotData = data;
  if (data?.tradeDate) state.hotspotSelectedDate = data.tradeDate;
  const summary = data?.summary || {};
  $("hotspotUniverse").textContent = summary.eligibleStocks ?? "-";
  $("hotspotTriggered").textContent = summary.triggeredStocks ?? "-";
  $("hotspotCoverage").textContent = summary.moneyflowCoverage == null ? "-" : hotspotPercent(summary.moneyflowCoverage);
  $("hotspotBlocks").textContent = summary.blockTradeStocks ?? "-";
  renderHotspotSectors(data?.sectors || []);
  renderHotspotStocks();
  if (data?.tradeDate) {
    updateHotspotDateControls();
    setHotspotJob(`已加载 ${formatHotspotDate(data.tradeDate)} 日终扫描结果`);
  }
}

function formatHotspotDate(value) {
  return String(value || "").replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3");
}

function hotspotMonthFromDate(value) {
  const match = String(value || "").match(/^(\d{4})(\d{2})\d{2}$/);
  return match ? new Date(Number(match[1]), Number(match[2]) - 1, 1) : new Date(new Date().getFullYear(), new Date().getMonth(), 1);
}

function hotspotMonthNumber(date) {
  return date.getFullYear() * 12 + date.getMonth();
}

function updateHotspotDateControls() {
  const selected = state.hotspotSelectedDate;
  const scanned = state.hotspotScannedDates.includes(selected);
  $("hotspotDateLabel").textContent = selected ? formatHotspotDate(selected) : "选择交易日";
  $("runHotspotLabel").textContent = scanned ? "重新生成该日热点榜" : "生成所选日期热点榜";
  renderHotspotCalendar();
}

function renderHotspotCalendar() {
  const grid = $("hotspotCalendarGrid");
  if (!grid) return;
  const available = new Set(state.hotspotAvailableDates);
  const scanned = new Set(state.hotspotScannedDates);
  const month = state.hotspotCalendarMonth || hotspotMonthFromDate(state.hotspotSelectedDate);
  state.hotspotCalendarMonth = month;
  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  $("hotspotCalendarTitle").textContent = `${year}年 ${monthIndex + 1}月`;
  const dayCount = new Date(year, monthIndex + 1, 0).getDate();
  const offset = (new Date(year, monthIndex, 1).getDay() + 6) % 7;
  const today = new Date();
  const todayKey = `${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, "0")}${String(today.getDate()).padStart(2, "0")}`;
  grid.innerHTML = Array.from({ length: dayCount }, (_, index) => {
    const day = index + 1;
    const key = `${year}${String(monthIndex + 1).padStart(2, "0")}${String(day).padStart(2, "0")}`;
    const hasData = available.has(key);
    const isScanned = scanned.has(key);
    const classes = [hasData ? "available" : "", isScanned ? "scanned" : "", key === state.hotspotSelectedDate ? "selected" : "", key === todayKey ? "today" : ""].filter(Boolean).join(" ");
    const firstStyle = index === 0 ? ` style="grid-column-start:${offset + 1}"` : "";
    const title = isScanned ? "已生成热点榜" : hasData ? "已有行情缓存，点击选择" : "无本地数据";
    return `<button type="button" class="${classes}" data-date="${key}" title="${title}"${firstStyle}${hasData ? "" : " disabled"}>${day}</button>`;
  }).join("");

  const monthNumbers = state.hotspotAvailableDates.map((date) => hotspotMonthNumber(hotspotMonthFromDate(date)));
  const current = hotspotMonthNumber(month);
  $("hotspotPrevMonth").disabled = !monthNumbers.length || current <= Math.min(...monthNumbers);
  $("hotspotNextMonth").disabled = !monthNumbers.length || current >= Math.max(...monthNumbers);
}

function showHotspotPending(date) {
  state.hotspotData = null;
  for (const id of ["hotspotUniverse", "hotspotTriggered", "hotspotCoverage", "hotspotBlocks"]) $(id).textContent = "-";
  $("hotspotSectorBody").innerHTML = '<tr><td colspan="6" class="table-empty">该日期尚未生成行业热点榜</td></tr>';
  $("hotspotStockBody").innerHTML = '<tr><td colspan="9" class="table-empty">点击“生成所选日期热点榜”后显示</td></tr>';
  setHotspotJob(`${formatHotspotDate(date)} 已有全市场行情缓存，尚未生成热点榜`);
}

async function selectHotspotDate(date) {
  if (!state.hotspotAvailableDates.includes(date)) return;
  state.hotspotSelectedDate = date;
  state.hotspotCalendarMonth = hotspotMonthFromDate(date);
  $("hotspotCalendarPanel").hidden = true;
  $("hotspotCalendarToggle").setAttribute("aria-expanded", "false");
  updateHotspotDateControls();
  if (state.hotspotScannedDates.includes(date)) await loadHotspot(date);
  else showHotspotPending(date);
}

async function loadHotspot(date = "") {
  const query = date ? `?date=${encodeURIComponent(date)}` : "";
  const data = await requestJson(`/api/hotspots${query}`);
  renderHotspot(data);
}

async function loadHotspotDates(preferred = "") {
  const data = await requestJson("/api/hotspots/dates");
  state.hotspotAvailableDates = data.dates || [];
  state.hotspotScannedDates = data.scannedDates || data.dates || [];
  const requested = preferred || state.hotspotSelectedDate;
  const selected = state.hotspotAvailableDates.includes(requested)
    ? requested
    : state.hotspotScannedDates[0] || state.hotspotAvailableDates[0] || "";
  state.hotspotSelectedDate = selected;
  state.hotspotCalendarMonth = hotspotMonthFromDate(selected);
  updateHotspotDateControls();
  if (!selected) {
    setHotspotJob("本地数据库暂无可用交易日", "error");
  } else if (state.hotspotScannedDates.includes(selected)) {
    await loadHotspot(selected);
  } else {
    showHotspotPending(selected);
  }
}

async function pollHotspotJob(jobId) {
  state.hotspotJobId = jobId;
  const button = $("runHotspotBtn");
  button.disabled = true;
  try {
    for (;;) {
      const job = await requestJson(`/api/hotspots/jobs/${encodeURIComponent(jobId)}`);
      setHotspotJob(`${job.message || job.stage} · ${Number(job.progress || 0).toFixed(0)}%`, job.status === "failed" ? "error" : "running");
      if (job.status === "complete") {
        await loadHotspotDates(job.tradeDate);
        return;
      }
      if (job.status === "failed") throw new Error(job.error || "热点扫描失败");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } finally {
    state.hotspotJobId = null;
    button.disabled = false;
  }
}

async function runHotspotScan() {
  const tradeDate = state.hotspotSelectedDate || null;
  if (!tradeDate) throw new Error("请先从热点日历选择一个有数据的交易日");
  const response = await fetch("/api/hotspots/scan", {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tradeDate }),
  });
  const job = await response.json();
  if (!response.ok && response.status !== 409) throw new Error(job.detail || job.error || `HTTP ${response.status}`);
  await pollHotspotJob(job.jobId);
}

async function analyzeHotspotTicker(ticker) {
  if (!ticker) return;
  const rawDate = state.hotspotData?.tradeDate || $("dateInput").value;
  const date = String(rawDate).replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3");
  $("tickerInput").value = ticker;
  $("dateInput").value = date;
  const needsReportList = !state.singleWorkspaceInitialized;
  if (needsReportList) state.singleWorkspaceInitialized = true;
  setWorkspace("single", "#market");
  window.location.hash = "market";
  setStatus(`正在接入 ${ticker} 的单股量化与财务分析`);
  await Promise.all([runQuant(), loadFundamentals(ticker, date)]);
  if (needsReportList) {
    try {
      await loadReports(false);
    } catch (error) {
      state.singleWorkspaceInitialized = false;
      setStatus(`历史报告列表加载失败：${error.message}`, "error");
    }
  }
}

function setWorkspace(mode, activeHash = window.location.hash) {
  const workspace = mode === "hotspot" ? "hotspot" : "single";
  document.body.dataset.workspace = workspace;
  document.querySelectorAll("nav a[data-workspace-target]").forEach((link) => {
    const isActive = workspace === "hotspot"
      ? link.dataset.workspaceTarget === "hotspot"
      : link.dataset.workspaceTarget === "single"
        && (link.closest(".mobile-workspace-nav") || link.getAttribute("href") === activeHash);
    link.classList.toggle("active", isActive);
  });
  if (workspace === "single" && !document.querySelector("nav a.active[data-workspace-target]")) {
    document.querySelectorAll('nav a[href="#overview"]').forEach((link) => link.classList.add("active"));
  }
  initializeWorkspace(workspace);
}

function initializeWorkspace(workspace) {
  if (workspace === "hotspot") {
    if (state.hotspotWorkspaceInitialized) return;
    state.hotspotWorkspaceInitialized = true;
    loadHotspotDates().catch((error) => {
      state.hotspotWorkspaceInitialized = false;
      setHotspotJob(`热点雷达初始化失败：${error.message}`, "error");
    });
    return;
  }
  if (state.singleWorkspaceInitialized) return;
  state.singleWorkspaceInitialized = true;
  loadReports().catch((error) => {
    state.singleWorkspaceInitialized = false;
    setStatus(`初始化失败：${error.message}`, "error");
    updateDashboard(null);
  });
}

async function loadReport(reportId) {
  if (!reportId) return;
  setStatus("加载报告中");
  state.liveQuant = null;
  state.fundamentalSnapshot = null;
  const report = await requestJson(`/api/reports/${encodeURIComponent(reportId)}`);
  state.activeReport = report;
  updateDashboard(report);
  await loadFundamentals(report.ticker, report.analysisDate, true);
}

async function loadFundamentals(ticker, date, silent = false) {
  if (!ticker || !date) return;
  const button = $("refreshFundamentalsBtn");
  button.disabled = true;
  updateFundamentalView(null, true);
  if (!silent) setStatus(`读取 ${ticker} 的 Tushare 财务数据中`);
  try {
    const snapshot = await requestJson(`/api/fundamentals/${encodeURIComponent(ticker)}?date=${encodeURIComponent(date)}`);
    state.fundamentalSnapshot = snapshot;
    updateFundamentalView(snapshot);
    $("sourceFundamentals").textContent = snapshot.cached ? "Tushare 缓存" : "Tushare";
    if (state.activeReport?.ticker === ticker && snapshot.company?.name) {
      $("pageTitle").textContent = `${snapshot.company.name} · ${ticker}`;
    }
    setStatus(`已加载 ${ticker} 的报告与财务快照`);
  } catch (error) {
    state.fundamentalSnapshot = null;
    updateFundamentalView(null);
    $("sourceFundamentals").textContent = "失败";
    setStatus(`财务数据失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

async function loadReports(loadFirst = true) {
  const data = await requestJson("/api/reports");
  state.reports = data.reports || [];
  const select = $("reportSelect");
  select.innerHTML = state.reports
    .map((report) => `<option value="${escapeHtml(report.id)}">${escapeHtml(report.id)}</option>`)
    .join("");
  if (!state.reports.length) {
    if (loadFirst) {
      setStatus("reports 目录下还没有可读取的 complete_report.md", "error");
      updateDashboard(null);
    }
    return;
  }
  if (loadFirst) await loadReport(state.reports[0].id);
}

async function runQuant() {
  const ticker = $("tickerInput").value.trim().toUpperCase();
  const date = $("dateInput").value;
  if (!ticker || !date) {
    setStatus("需要股票代码和日期才能生成实时策略", "error");
    return;
  }
  const button = $("runQuantBtn");
  button.disabled = true;
  setStatus(`生成 ${ticker} 的实时量化策略中`);
  try {
    const data = await requestJson(`/api/quant/${encodeURIComponent(ticker)}?date=${encodeURIComponent(date)}`);
    state.liveQuant = data;
    state.activeSection = "quant";
    if (!state.activeReport || state.activeReport.ticker !== ticker) {
      state.activeReport = {
        ticker,
        analysisDate: date,
        modified: data.generatedAt,
        signal: "UNKNOWN",
        sections: {},
        quantSummary: data.summary,
      };
    } else {
      state.activeReport.analysisDate = date;
      state.activeReport.modified = data.generatedAt;
      state.activeReport.quantSummary = data.summary;
    }
    updateDashboard(state.activeReport);
    setStatus(`实时策略已生成 ${data.generatedAt}`);
  } catch (error) {
    setStatus(`实时策略失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

function bindEvents() {
  $("reportSelect").addEventListener("change", (event) => loadReport(event.target.value).catch((error) => setStatus(error.message, "error")));
  $("runQuantBtn").addEventListener("click", () => runQuant());
  $("refreshFundamentalsBtn").addEventListener("click", () => {
    const ticker = $("tickerInput").value.trim().toUpperCase();
    const date = $("dateInput").value;
    loadFundamentals(ticker, date).catch((error) => setStatus(error.message, "error"));
  });
  $("tabbar").addEventListener("click", (event) => {
    const button = event.target.closest(".tab");
    if (!button) return;
    state.activeSection = button.dataset.section;
    updateTabs();
  });
  $("runHotspotBtn").addEventListener("click", () => {
    runHotspotScan().catch((error) => setHotspotJob(error.message, "error"));
  });
  $("hotspotCalendarToggle").addEventListener("click", () => {
    const panel = $("hotspotCalendarPanel");
    panel.hidden = !panel.hidden;
    $("hotspotCalendarToggle").setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) renderHotspotCalendar();
  });
  $("hotspotPrevMonth").addEventListener("click", () => {
    const current = state.hotspotCalendarMonth || new Date();
    state.hotspotCalendarMonth = new Date(current.getFullYear(), current.getMonth() - 1, 1);
    renderHotspotCalendar();
  });
  $("hotspotNextMonth").addEventListener("click", () => {
    const current = state.hotspotCalendarMonth || new Date();
    state.hotspotCalendarMonth = new Date(current.getFullYear(), current.getMonth() + 1, 1);
    renderHotspotCalendar();
  });
  $("hotspotCalendarGrid").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-date]:not(:disabled)");
    if (button) selectHotspotDate(button.dataset.date).catch((error) => setHotspotJob(error.message, "error"));
  });
  $("hotspotSort").addEventListener("change", () => renderHotspotStocks());
  $("hotspotViewTabs").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-view]");
    if (!button) return;
    state.hotspotView = button.dataset.view;
    document.querySelectorAll("#hotspotViewTabs button").forEach((item) => item.classList.toggle("active", item === button));
    renderHotspotStocks();
  });
  $("hotspotStockBody").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-ticker]");
    if (button) analyzeHotspotTicker(button.dataset.ticker).catch((error) => setStatus(error.message, "error"));
  });
  $("chartRangeControls").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-days]");
    if (button) setChartRange(Number(button.dataset.days));
  });
  $("flowChart").addEventListener("mousemove", (event) => {
    if (!flowChartModel) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const index = Math.floor((x - flowChartModel.left) / flowChartModel.step);
    if (index < 0 || index >= flowChartModel.count || index === state.chartHoverIndex) return;
    state.chartHoverIndex = index;
    const quant = state.liveQuant?.summary || state.activeReport?.quantSummary || {};
    drawChart(quant.rows || []);
  });
  $("flowChart").addEventListener("mouseleave", () => {
    if (state.chartHoverIndex == null) return;
    state.chartHoverIndex = null;
    const quant = state.liveQuant?.summary || state.activeReport?.quantSummary || {};
    drawChart(quant.rows || []);
  });
  $("flowChart").addEventListener("wheel", (event) => {
    event.preventDefault();
    const ranges = [10, 20, 30, 60, 0];
    const current = Math.max(0, ranges.indexOf(state.chartRange));
    const next = Math.max(0, Math.min(ranges.length - 1, current + (event.deltaY > 0 ? 1 : -1)));
    if (next !== current) setChartRange(ranges[next]);
  }, { passive: false });
  window.addEventListener("resize", () => {
    const quant = state.liveQuant?.summary || state.activeReport?.quantSummary || {};
    drawChart(quant.rows || []);
    drawBacktestChart(quant.backtestTrades || []);
    drawFundamentalChart(state.fundamentalSnapshot?.trends || []);
  });
  document.addEventListener("click", (event) => {
    const workspaceLink = event.target.closest("a[data-workspace-target]");
    if (workspaceLink) setWorkspace(workspaceLink.dataset.workspaceTarget, workspaceLink.getAttribute("href"));
    if (!event.target.closest(".hotspot-calendar")) {
      $("hotspotCalendarPanel").hidden = true;
      $("hotspotCalendarToggle").setAttribute("aria-expanded", "false");
    }
  });
  window.addEventListener("hashchange", () => {
    setWorkspace(window.location.hash === "#hotspots" ? "hotspot" : "single", window.location.hash);
  });
}

setWorkspace(window.location.hash === "#hotspots" ? "hotspot" : "single", window.location.hash);
bindEvents();
