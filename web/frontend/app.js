const state = {
  reports: [],
  activeReport: null,
  activeSection: "complete",
  liveQuant: null,
  fundamentalSnapshot: null,
};

const $ = (id) => document.getElementById(id);

function setStatus(text, kind = "neutral") {
  const node = $("statusLine");
  node.textContent = text;
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
    ACTIVE_BUY_OR_HOLD: "买入 / 持有",
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
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(640, Math.floor(rect.width * dpr));
  canvas.height = Math.max(260, Math.floor(rect.height * dpr));
  return dpr;
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
  ctx.fillStyle = "#090d10";
  ctx.fillRect(0, 0, w, h);

  const left = 56;
  const right = 18;
  const top = 20;
  const bottom = 42;
  const plotW = w - left - right;
  const plotH = h - top - bottom;

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const y = top + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotW, y);
    ctx.stroke();
  }

  const parsed = (rows || [])
    .map((row) => ({
      date: row.date,
      close: parseNumber(row.close),
      net: parseNumber(row.netInflow),
      ratio: parsePercent(row.inflowRatio),
      signal: row.signal,
    }))
    .filter((row) => row.close != null || row.net != null);

  if (!parsed.length) {
    ctx.fillStyle = "#8c9aa7";
    ctx.font = "13px system-ui";
    ctx.fillText("暂无量化序列，生成实时策略后会显示资金异动图。", left, top + 48);
    $("chartBadge").className = "badge neutral";
    $("chartBadge").textContent = "NO DATA";
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    return;
  }

  const maxAbsNet = Math.max(...parsed.map((row) => Math.abs(row.net || 0)), 1);
  const closes = parsed.map((row) => row.close).filter((n) => n != null);
  const minClose = Math.min(...closes);
  const maxClose = Math.max(...closes);
  const closeRange = Math.max(maxClose - minClose, 0.01);
  const barGap = 6;
  const barW = Math.max(5, plotW / parsed.length - barGap);
  const zeroY = top + plotH * 0.62;

  ctx.strokeStyle = "rgba(215,179,106,0.45)";
  ctx.setLineDash([5, 5]);
  const thresholdY = top + plotH * 0.22;
  ctx.beginPath();
  ctx.moveTo(left, thresholdY);
  ctx.lineTo(left + plotW, thresholdY);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#d7b36a";
  ctx.font = "11px system-ui";
  ctx.fillText("5% threshold", left + 4, thresholdY - 7);

  parsed.forEach((row, index) => {
    const x = left + index * (plotW / parsed.length) + barGap / 2;
    const barH = Math.abs((row.net || 0) / maxAbsNet) * plotH * 0.46;
    const y = row.net >= 0 ? zeroY - barH : zeroY;
    ctx.fillStyle = row.net >= 0 ? "rgba(103,211,145,0.78)" : "rgba(255,111,111,0.72)";
    ctx.fillRect(x, y, barW, Math.max(2, barH));
    if (index % Math.ceil(parsed.length / 5) === 0) {
      ctx.fillStyle = "#5d6b77";
      ctx.font = "10px system-ui";
      ctx.fillText(row.date.slice(5), x, h - 16);
    }
  });

  ctx.strokeStyle = "#5cc9d8";
  ctx.lineWidth = 2;
  ctx.beginPath();
  parsed.forEach((row, index) => {
    if (row.close == null) return;
    const x = left + index * (plotW / parsed.length) + barW / 2;
    const y = top + plotH - ((row.close - minClose) / closeRange) * plotH;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.strokeStyle = "rgba(255,255,255,0.18)";
  ctx.beginPath();
  ctx.moveTo(left, top);
  ctx.lineTo(left, top + plotH);
  ctx.lineTo(left + plotW, top + plotH);
  ctx.stroke();

  const hasSignal = parsed.some((row) => String(row.signal || "").toUpperCase().includes("BUY"));
  $("chartBadge").className = hasSignal ? "badge signal" : "badge watch";
  $("chartBadge").textContent = hasSignal ? "INFLOW SIGNAL" : "WATCH";
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
  ctx.fillStyle = "#090d10";
  ctx.fillRect(0, 0, w, h);

  const rows = (trends || []).filter((row) => row.revenue != null || row.netProfit != null || row.operatingCashFlow != null);
  const left = 58;
  const right = 58;
  const top = 38;
  const bottom = 42;
  const plotW = w - left - right;
  const plotH = h - top - bottom;

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const y = top + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotW, y);
    ctx.stroke();
  }

  if (!rows.length) {
    ctx.fillStyle = "#8c9aa7";
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

  ctx.fillStyle = "rgba(92,201,216,0.62)";
  rows.forEach((row, index) => {
    const revenue = Number(row.revenue) || 0;
    const x = left + slot * index + (slot - barW) / 2;
    const barH = (Math.abs(revenue) / revenueMax) * plotH * 0.88;
    ctx.fillRect(x, top + plotH - barH, barW, Math.max(2, barH));
    ctx.fillStyle = "#5d6b77";
    ctx.font = "10px system-ui";
    ctx.fillText(periodLabel(row.period), x - 2, h - 16);
    ctx.fillStyle = "rgba(92,201,216,0.62)";
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
  drawLine("netProfit", "#67d391");
  drawLine("operatingCashFlow", "#d7b36a");

  ctx.fillStyle = "#5cc9d8";
  ctx.fillRect(left, 13, 12, 7);
  ctx.fillStyle = "#8c9aa7";
  ctx.font = "11px system-ui";
  ctx.fillText("累计营收", left + 18, 21);
  ctx.strokeStyle = "#67d391";
  ctx.beginPath();
  ctx.moveTo(left + 92, 17);
  ctx.lineTo(left + 106, 17);
  ctx.stroke();
  ctx.fillText("归母净利润", left + 111, 21);
  ctx.strokeStyle = "#d7b36a";
  ctx.beginPath();
  ctx.moveTo(left + 191, 17);
  ctx.lineTo(left + 205, 17);
  ctx.stroke();
  ctx.fillText("经营现金流", left + 210, 21);

  ctx.fillStyle = "#5d6b77";
  ctx.font = "10px system-ui";
  ctx.fillText(`${(revenueMax / 100_000_000).toFixed(1)}亿`, 8, top + 5);
  ctx.fillText(`${(profitMax / 100_000_000).toFixed(1)}亿`, w - right + 8, top + 5);
  ctx.fillText(`${(profitMin / 100_000_000).toFixed(1)}亿`, w - right + 8, top + plotH);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
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
  $("metricDay0").textContent = quant.day0 || "-";
  $("metricNetInflow").textContent = `净流入 ${quant.netInflow || "-"}`;
  $("metricLevels").textContent = [quant.takeProfit, quant.riskExit].filter(Boolean).join(" / ") || "-";
  $("metricLatestClose").textContent = `最新收盘 ${quant.latestClose || "-"}`;
  $("metricDecision").textContent = decision;
  $("metricModified").textContent = report?.modified ? `更新 ${report.modified}` : "-";

  $("sourceReport").textContent = report ? "已加载" : "-";
  $("sourceQuant").textContent = state.liveQuant ? "实时生成" : report?.sections?.quant ? "报告内" : "未生成";
  $("sourceFundamentals").textContent = state.fundamentalSnapshot ? "Tushare" : "未加载";
  $("sourceLog").textContent = report?.sections?.fetchLog ? "已记录" : "无";

  $("policyDigest").innerHTML = digestFromSections(report)
    .map((item) => `<div class="digest-item"><b>${escapeHtml(item.label)}</b><span>${escapeHtml(item.text)}</span></div>`)
    .join("");

  drawChart(quant.rows || []);
  updateFundamentalView(state.fundamentalSnapshot);
  updateTabs();
}

async function requestJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  }
  return data;
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

async function loadReports() {
  const data = await requestJson("/api/reports");
  state.reports = data.reports || [];
  const select = $("reportSelect");
  select.innerHTML = state.reports
    .map((report) => `<option value="${escapeHtml(report.id)}">${escapeHtml(report.id)}</option>`)
    .join("");
  if (!state.reports.length) {
    setStatus("reports 目录下还没有可读取的 complete_report.md", "error");
    updateDashboard(null);
    return;
  }
  await loadReport(state.reports[0].id);
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
    if (!state.activeReport) {
      state.activeReport = {
        ticker,
        analysisDate: date,
        modified: data.generatedAt,
        signal: "UNKNOWN",
        sections: {},
        quantSummary: data.summary,
      };
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
  window.addEventListener("resize", () => {
    drawChart((state.liveQuant?.summary || state.activeReport?.quantSummary || {}).rows || []);
    drawFundamentalChart(state.fundamentalSnapshot?.trends || []);
  });
}

bindEvents();
loadReports().catch((error) => {
  setStatus(`初始化失败：${error.message}`, "error");
  updateDashboard(null);
});
