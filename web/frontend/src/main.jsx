import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Building2,
  CalendarDays,
  Check,
  ChevronDown,
  Database,
  Download,
  FileText,
  Flame,
  Gauge,
  History,
  Info,
  Bell,
  LineChart as LineChartIcon,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  Target,
  Trash2,
  Trophy,
  WalletCards,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import avatarUrl from "../nailong-avatar.png";
import "./styles.css";

const SECTIONS = [
  ["complete", "总报告"],
  ["quant", "量化策略"],
  ["market", "行情"],
  ["news", "新闻政策"],
  ["fundamentals", "基本面"],
  ["sentiment", "情绪"],
  ["portfolio", "组合决策"],
  ["fetchLog", "抓取日志"],
];

const CHART_GREEN = "#238b68";
const CHART_BLACK = "#282720";
const MUTED = "#776f66";

function workspaceFromHash() {
  if (window.location.hash === "#hotspots") return "hotspot";
  if (window.location.hash === "#portfolio") return "portfolio";
  return "single";
}

function numberFrom(value) {
  if (value == null || value === "") return null;
  const match = String(value).replaceAll(",", "").match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function percentFrom(value) {
  return numberFrom(value);
}

function formatMoney(value) {
  if (value == null || !Number.isFinite(Number(value))) return "-";
  const n = Number(value);
  const abs = Math.abs(n);
  if (abs >= 100_000_000) return `${(n / 100_000_000).toFixed(2)} 亿`;
  if (abs >= 10_000) return `${(n / 10_000).toFixed(1)} 万`;
  return n.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function formatMetric(value, suffix = "", digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return "-";
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function formatPercentText(value, signed = false) {
  const n = percentFrom(value);
  if (n == null) return "-";
  return `${signed && n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function formatChange(value) {
  const n = numberFrom(value);
  if (n == null) return "同比 -";
  return `同比 ${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function signalLabel(value) {
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

function signalTone(value) {
  const v = String(value || "").toUpperCase();
  if (v.includes("BUY") || v.includes("买")) return "positive";
  if (v.includes("SELL") || v.includes("卖") || v.includes("RISK") || v.includes("EXIT")) return "negative";
  if (v.includes("HOLD") || v.includes("WATCH") || v.includes("观望")) return "watch";
  if (v.includes("ERROR") || v.includes("UNAVAILABLE")) return "error";
  return "neutral";
}

function isExitSignal(value) {
  return ["REDUCE_OR_EXIT", "SELL_TAKE_PROFIT", "EXPIRED"].includes(String(value || "").toUpperCase());
}

function exitPriceHint(quant, exitSignal) {
  if (!exitSignal) {
    return quant.takeProfit ? `止盈 ${quant.takeProfit}` : `最新收盘 ${quant.latestClose || "-"}`;
  }
  const signal = String(quant.signal || "").toUpperCase();
  if (signal === "SELL_TAKE_PROFIT") {
    return quant.takeProfit ? `已触发止盈 ${quant.takeProfit}` : "已触发止盈规则";
  }
  if (signal === "EXPIRED") return "信号已过期";
  const trigger = quant.currentExit || quant.riskExit;
  return trigger ? `已触发风控 ${trigger}` : "已触发退场规则";
}

function parseFlowRows(rows = []) {
  return rows
    .map((row) => ({
      date: row.date,
      close: numberFrom(row.close),
      net: numberFrom(row.netInflow),
      signal: row.signal,
    }))
    .filter((row) => row.close != null || row.net != null);
}

function markdownToBlocks(markdown) {
  if (!markdown || !markdown.trim()) return [{ type: "empty", text: "当前报告没有这一部分内容" }];
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let list = [];
  const flushList = () => {
    if (list.length) blocks.push({ type: "list", items: list.splice(0) });
  };
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      continue;
    }
    if (/^#{1,3}\s+/.test(trimmed)) {
      flushList();
      const level = trimmed.match(/^#+/)[0].length;
      blocks.push({ type: `h${level}`, text: trimmed.replace(/^#{1,3}\s+/, "") });
    } else if (/^[-*]\s+/.test(trimmed)) {
      list.push(trimmed.replace(/^[-*]\s+/, ""));
    } else {
      flushList();
      blocks.push({ type: "p", text: trimmed });
    }
  }
  flushList();
  return blocks;
}

function api(url, options = {}) {
  return fetch(url, { cache: "no-store", ...options }).then(async (response) => {
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    return data;
  });
}

function App() {
  const [workspace, setWorkspace] = useState(workspaceFromHash);
  const [reports, setReports] = useState([]);
  const [activeReport, setActiveReport] = useState(null);
  const [liveQuant, setLiveQuant] = useState(null);
  const [fundamentals, setFundamentals] = useState(null);
  const [personalBoard, setPersonalBoard] = useState(null);
  const [activeSection, setActiveSection] = useState("complete");
  const [ticker, setTicker] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [status, setStatus] = useState({ text: "Agent: initializing dashboard.", tone: "neutral" });
  const [personalStatus, setPersonalStatus] = useState({ text: "Agent: personal board idle.", tone: "neutral" });
  const [fundLoading, setFundLoading] = useState(false);
  const [quantLoading, setQuantLoading] = useState(false);
  const [personalLoading, setPersonalLoading] = useState(false);
  const [personalRefreshing, setPersonalRefreshing] = useState(false);
  const [chartRange, setChartRange] = useState(30);
  const [hotspot, setHotspot] = useState({
    data: null,
    view: "stocks",
    sort: "stock_score",
    availableDates: [],
    scannedDates: [],
    tradingDates: [],
    latestTradeDate: "",
    selectedDate: "",
    month: new Date(),
    job: { text: "Agent: hotspot radar idle.", tone: "neutral" },
    running: false,
  });

  const quant = liveQuant?.summary || activeReport?.quantSummary || {};
  const flowRows = useMemo(() => {
    const rows = parseFlowRows(quant.rows || []);
    return chartRange > 0 ? rows.slice(-chartRange) : rows;
  }, [quant.rows, chartRange]);

  useEffect(() => {
    const onHash = () => setWorkspace(workspaceFromHash());
    window.addEventListener("hashchange", onHash);
    loadReports();
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (workspace === "hotspot" && !hotspot.availableDates.length && !hotspot.scannedDates.length) {
      loadHotspotDates().catch((error) => setHotspotJob(`Agent: hotspot init failed. ${error.message}`, "error"));
    }
  }, [workspace]);

  useEffect(() => {
    if (workspace === "portfolio" && !personalBoard && !personalLoading) {
      loadPersonalBoard();
    }
  }, [workspace, personalBoard, personalLoading]);

  async function loadReports(loadFirst = true) {
    try {
      const data = await api("/api/reports");
      const list = data.reports || [];
      setReports(list);
      if (!list.length) {
        setStatus({ text: "Agent: no complete_report.md found under reports.", tone: "error" });
        return;
      }
      if (loadFirst) await loadReport(list[0].id);
    } catch (error) {
      setStatus({ text: `Agent: initialization failed. ${error.message}`, tone: "error" });
    }
  }

  async function loadReport(reportId) {
    if (!reportId) return;
    setStatus({ text: "Agent: loading report.", tone: "running" });
    setLiveQuant(null);
    setFundamentals(null);
    const report = await api(`/api/reports/${encodeURIComponent(reportId)}`);
    setActiveReport({ ...report, id: report.id || reportId });
    setTicker(report.ticker || "");
    setDate(report.analysisDate || date);
    setActiveSection("complete");
    setStatus({ text: "Agent: report loaded.", tone: "success" });
    await loadFundamentals(report.ticker, report.analysisDate, true);
  }

  async function loadFundamentals(nextTicker = ticker, nextDate = date, silent = false) {
    if (!nextTicker || !nextDate) return;
    setFundLoading(true);
    if (!silent) setStatus({ text: `Agent: reading fundamentals for ${nextTicker}.`, tone: "running" });
    try {
      const snapshot = await api(`/api/fundamentals/${encodeURIComponent(nextTicker)}?date=${encodeURIComponent(nextDate)}`);
      setFundamentals(snapshot);
      setStatus({ text: `Agent: fundamentals complete for ${nextTicker}.`, tone: "success" });
    } catch (error) {
      setFundamentals(null);
      setStatus({ text: `Agent: fundamentals failed. ${error.message}`, tone: "error" });
    } finally {
      setFundLoading(false);
    }
  }

  async function runQuant() {
    const nextTicker = ticker.trim().toUpperCase();
    if (!nextTicker || !date) {
      setStatus({ text: "Agent: ticker and date are required.", tone: "error" });
      return;
    }
    setQuantLoading(true);
    setStatus({ text: `Agent: generating quant strategy for ${nextTicker}.`, tone: "running" });
    try {
      const data = await api(`/api/quant/${encodeURIComponent(nextTicker)}?date=${encodeURIComponent(date)}`);
      setLiveQuant(data);
      setActiveSection("quant");
      setActiveReport((current) => ({
        ...(current || {}),
        ticker: nextTicker,
        analysisDate: date,
        modified: data.generatedAt,
        signal: current?.signal || "UNKNOWN",
        sections: current?.sections || {},
        quantSummary: data.summary,
      }));
      setStatus({ text: `Agent: quant strategy complete. ${data.generatedAt}`, tone: "success" });
    } catch (error) {
      setStatus({ text: `Agent: quant strategy failed. ${error.message}`, tone: "error" });
    } finally {
      setQuantLoading(false);
    }
  }

  function setHotspotJob(text, tone = "neutral") {
    setHotspot((current) => ({ ...current, job: { text, tone } }));
  }

  function formatHotspotDate(value) {
    return String(value || "").replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3");
  }

  function monthFromHotspot(value) {
    const match = String(value || "").match(/^(\d{4})(\d{2})\d{2}$/);
    return match ? new Date(Number(match[1]), Number(match[2]) - 1, 1) : new Date();
  }

  async function loadHotspotDates(preferred = "") {
    const data = await api("/api/hotspots/dates");
    const availableDates = data.dates || [];
    const scannedDates = data.scannedDates || data.dates || [];
    const tradingDates = data.tradeDates || [];
    const latestTradeDate = data.latestTradeDate || scannedDates[0] || availableDates[0] || "";
    const selectable = new Set([...availableDates, ...tradingDates, latestTradeDate].filter(Boolean));
    const selectedDate = selectable.has(preferred) ? preferred : latestTradeDate || scannedDates[0] || availableDates[0] || "";
    setHotspot((current) => ({
      ...current,
      availableDates,
      scannedDates,
      tradingDates,
      latestTradeDate,
      selectedDate,
      month: monthFromHotspot(selectedDate),
    }));
    if (!selectedDate) setHotspotJob("Agent: no local trading dates available.", "error");
    else if (scannedDates.includes(selectedDate)) await loadHotspot(selectedDate);
    else showHotspotPending(selectedDate, availableDates);
  }

  function showHotspotPending(selectedDate, availableDates = hotspot.availableDates) {
    const hasCache = availableDates.includes(selectedDate);
    setHotspot((current) => ({ ...current, data: null, selectedDate }));
    setHotspotJob(
      hasCache
        ? `Agent: ${formatHotspotDate(selectedDate)} cached, scan not generated.`
        : `Agent: ${formatHotspotDate(selectedDate)} not cached; ready to download and scan.`,
    );
  }

  async function loadHotspot(selectedDate = "") {
    const query = selectedDate ? `?date=${encodeURIComponent(selectedDate)}` : "";
    const data = await api(`/api/hotspots${query}`);
    setHotspot((current) => ({
      ...current,
      data,
      selectedDate: data?.tradeDate || current.selectedDate,
      month: monthFromHotspot(data?.tradeDate || current.selectedDate),
      job: { text: `Agent: loaded ${formatHotspotDate(data?.tradeDate)} hotspot scan.`, tone: "success" },
    }));
  }

  async function selectHotspotDate(selectedDate) {
    const selectable = new Set([...hotspot.availableDates, ...hotspot.tradingDates, hotspot.latestTradeDate].filter(Boolean));
    if (!selectable.has(selectedDate)) return;
    if (hotspot.scannedDates.includes(selectedDate)) await loadHotspot(selectedDate);
    else showHotspotPending(selectedDate);
    setHotspot((current) => ({ ...current, selectedDate, month: monthFromHotspot(selectedDate) }));
  }

  async function pollHotspotJob(jobId) {
    setHotspot((current) => ({ ...current, running: true }));
    try {
      for (;;) {
        const job = await api(`/api/hotspots/jobs/${encodeURIComponent(jobId)}`);
        setHotspotJob(`Agent: ${job.message || job.stage} · ${Number(job.progress || 0).toFixed(0)}%`, job.status === "failed" ? "error" : "running");
        if (job.status === "complete") {
          await loadHotspotDates(job.tradeDate);
          return;
        }
        if (job.status === "failed") throw new Error(job.error || "热点扫描失败");
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    } finally {
      setHotspot((current) => ({ ...current, running: false }));
    }
  }

  async function runHotspotScan() {
    if (!hotspot.selectedDate) {
      setHotspotJob("Agent: select a trading date first.", "error");
      return;
    }
    try {
      const response = await fetch("/api/hotspots/scan", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tradeDate: hotspot.selectedDate, refreshTarget: true }),
      });
      const job = await response.json();
      if (!response.ok && response.status !== 409) throw new Error(job.detail || job.error || `HTTP ${response.status}`);
      await pollHotspotJob(job.jobId);
    } catch (error) {
      setHotspotJob(`Agent: hotspot scan failed. ${error.message}`, "error");
    }
  }

  function exportHotspotHtml() {
    const tradeDate = hotspot.data?.tradeDate;
    if (!tradeDate) {
      setHotspotJob("Agent: generate a hotspot scan before export.", "error");
      return;
    }
    const link = document.createElement("a");
    link.href = `/api/hotspots/export?date=${encodeURIComponent(tradeDate)}`;
    link.download = `a-share-hotspot-${tradeDate}.html`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  async function analyzeHotspotTicker(nextTicker) {
    if (!nextTicker) return;
    const nextDate = formatHotspotDate(hotspot.data?.tradeDate || hotspot.selectedDate || date);
    setTicker(nextTicker);
    setDate(nextDate);
    window.location.hash = "#market";
    setWorkspace("single");
    setStatus({ text: `Agent: analyzing ${nextTicker}.`, tone: "running" });
    await Promise.all([runQuantFor(nextTicker, nextDate), loadFundamentals(nextTicker, nextDate)]);
  }

  async function runQuantFor(nextTicker, nextDate) {
    const data = await api(`/api/quant/${encodeURIComponent(nextTicker)}?date=${encodeURIComponent(nextDate)}`);
    setLiveQuant(data);
    setActiveReport((current) => ({
      ...(current || {}),
      ticker: nextTicker,
      analysisDate: nextDate,
      modified: data.generatedAt,
      signal: current?.signal || "UNKNOWN",
      sections: current?.sections || {},
      quantSummary: data.summary,
    }));
  }

  async function loadPersonalBoard() {
    setPersonalLoading(true);
    setPersonalStatus({ text: "Agent: loading personal board.", tone: "running" });
    try {
      const data = await api("/api/personal-board");
      setPersonalBoard(data);
      setPersonalStatus({ text: "Agent: personal board loaded.", tone: "success" });
    } catch (error) {
      setPersonalStatus({ text: `Agent: personal board failed. ${error.message}`, tone: "error" });
    } finally {
      setPersonalLoading(false);
    }
  }

  async function savePersonalBoard(nextBoard) {
    setPersonalLoading(true);
    setPersonalStatus({ text: "Agent: saving personal board.", tone: "running" });
    try {
      const data = await api("/api/personal-board", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(nextBoard),
      });
      setPersonalBoard(data);
      setPersonalStatus({ text: "Agent: personal board saved.", tone: "success" });
    } catch (error) {
      setPersonalStatus({ text: `Agent: save failed. ${error.message}`, tone: "error" });
    } finally {
      setPersonalLoading(false);
    }
  }

  async function refreshPersonalBoard() {
    setPersonalRefreshing(true);
    setPersonalStatus({ text: "Agent: refreshing holding monitor snapshots.", tone: "running" });
    try {
      const data = await api("/api/personal-board/refresh", { method: "POST" });
      setPersonalBoard(data);
      setPersonalStatus({ text: `Agent: refreshed ${data.refreshed?.length || 0} holdings.`, tone: "success" });
    } catch (error) {
      setPersonalStatus({ text: `Agent: refresh failed. ${error.message}`, tone: "error" });
    } finally {
      setPersonalRefreshing(false);
    }
  }

  function saveBoardList(listName, rows) {
    const nextBoard = { ...(personalBoard || {}), [listName]: rows };
    savePersonalBoard(nextBoard);
  }

  const latestClose = useMemo(() => {
    const closes = flowRows.map((row) => row.close).filter((value) => value != null);
    return numberFrom(quant.latestClose) ?? closes.at(-1) ?? null;
  }, [flowRows, quant.latestClose]);

  const previousClose = flowRows.map((row) => row.close).filter((value) => value != null).at(-2);
  const latestChange = latestClose != null && previousClose ? (latestClose / previousClose - 1) * 100 : null;
  const exitSignal = isExitSignal(quant.signal);

  return (
    <div className="app">
      <TopNav workspace={workspace} setWorkspace={setWorkspace} />
      <main className="shell">
        {workspace === "single" ? (
          <>
            <Sidebar
              reports={reports}
              activeReport={activeReport}
              ticker={ticker}
              date={date}
              status={status}
              quantLoading={quantLoading}
              fundLoading={fundLoading}
              onReport={(id) => loadReport(id).catch((error) => setStatus({ text: error.message, tone: "error" }))}
              setTicker={setTicker}
              setDate={setDate}
              runQuant={runQuant}
              refreshFundamentals={() => loadFundamentals()}
              source={{
                report: activeReport ? "已加载" : "-",
                quant: liveQuant ? "实时生成" : activeReport?.sections?.quant ? "报告内" : "未生成",
                fundamentals: fundamentals ? (fundamentals.cached ? "Tushare 缓存" : "Tushare") : "未加载",
                log: activeReport?.sections?.fetchLog ? "已记录" : "无",
              }}
            />
            <section className="content">
              <Hero
                report={activeReport}
                latestClose={latestClose}
                latestChange={latestChange}
                decision={activeReport?.signal || "UNKNOWN"}
                date={activeReport?.analysisDate || date}
              />
              <MetricStrip quant={quant} report={activeReport} exitSignal={exitSignal} />
              <QueryShowcase quant={quant} fundamentals={fundamentals} />
              <section id="market" className="grid two">
                <MarketChart rows={flowRows} range={chartRange} setRange={setChartRange} />
                <StrategyPanel quant={quant} exitSignal={exitSignal} />
              </section>
              <BacktestSection quant={quant} />
              <FundamentalsSection snapshot={fundamentals} loading={fundLoading} />
              <ReportSection
                report={activeReport}
                liveQuant={liveQuant}
                activeSection={activeSection}
                setActiveSection={setActiveSection}
              />
            </section>
          </>
        ) : workspace === "portfolio" ? (
          <PersonalWorkspace
            board={personalBoard}
            status={personalStatus}
            loading={personalLoading}
            refreshing={personalRefreshing}
            reports={reports}
            saveList={saveBoardList}
            refresh={refreshPersonalBoard}
            analyzeTicker={analyzeHotspotTicker}
          />
        ) : (
          <HotspotWorkspace
            hotspot={hotspot}
            setHotspot={setHotspot}
            selectDate={selectHotspotDate}
            runScan={runHotspotScan}
            exportHtml={exportHotspotHtml}
            analyzeTicker={analyzeHotspotTicker}
          />
        )}
      </main>
    </div>
  );
}

function TopNav({ workspace, setWorkspace }) {
  const navigate = (next, hash) => {
    setWorkspace(next);
    window.location.hash = hash;
  };
  return (
    <header className="topbar">
      <button className="brand" type="button" onClick={() => navigate("single", "#overview")}>
        <img src={avatarUrl} alt="TnT Nailong" />
        <span><b>TnT Nailong</b><small>Believe NaiLong Win Big Money</small></span>
      </button>
      <nav className="topnav">
        <button className={workspace === "single" ? "active" : ""} onClick={() => navigate("single", "#overview")} type="button"><LineChartIcon size={16} /> 单股量化</button>
        <button className={workspace === "hotspot" ? "active" : ""} onClick={() => navigate("hotspot", "#hotspots")} type="button"><Flame size={16} /> A股热点</button>
        <a href="#backtest"><Trophy size={16} /> 回测</a>
        <a href="#financials"><Building2 size={16} /> 财务</a>
        <a href="#research"><FileText size={16} /> 研报</a>
        <button className={workspace === "portfolio" ? "active" : ""} onClick={() => navigate("portfolio", "#portfolio")} type="button"><WalletCards size={16} /> 持仓 / 股票池</button>
      </nav>
      <div className="readonly"><span /> LOCAL · READ ONLY</div>
    </header>
  );
}

function Sidebar({ reports, activeReport, ticker, date, status, quantLoading, fundLoading, onReport, setTicker, setDate, runQuant, refreshFundamentals, source }) {
  return (
    <aside className="sidebar">
      <h2><BarChart3 size={21} /> 单股量化分析</h2>
      <label>历史报告</label>
      <select id="reportSelect" value={activeReport?.id || activeReport?.reportId || reports[0]?.id || ""} onChange={(event) => onReport(event.target.value)}>
        {reports.map((report) => <option key={report.id} value={report.id}>{report.id}</option>)}
      </select>
      <div className="field-row">
        <div><label>股票代码</label><input id="tickerInput" value={ticker} onChange={(event) => setTicker(event.target.value.toUpperCase())} /></div>
        <div><label>分析日期</label><input id="dateInput" type="date" value={date} onChange={(event) => setDate(event.target.value)} /></div>
      </div>
      <button id="runQuantBtn" className="primary" type="button" onClick={runQuant} disabled={quantLoading}>
        <Sparkles size={16} /> {quantLoading ? "生成中" : "生成量化策略"} <ArrowRight size={16} />
      </button>
      <button id="refreshFundamentalsBtn" className="secondary" type="button" onClick={refreshFundamentals} disabled={fundLoading}>
        <RefreshCw size={16} /> {fundLoading ? "刷新中" : "刷新财务快照"}
      </button>
      <AgentStatus status={status} />
      <section className="source-block">
        <h3><Database size={17} /> 数据源状态</h3>
        {Object.entries(source).map(([key, value]) => <p key={key}><span>{key}</span><b>{value}</b></p>)}
      </section>
      <div className="note"><ShieldCheck size={18} /> 仅提供入场与退场时机研究，不连接券商，不执行真实订单。</div>
    </aside>
  );
}

function AgentStatus({ status }) {
  return <div className={`agent ${status.tone || "neutral"}`}><Check size={15} /> {status.text}</div>;
}

function Hero({ report, latestClose, latestChange, decision, date }) {
  return (
    <motion.section id="overview" className="hero" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
      <div>
        <p className="eyebrow">VERIFIED LOCAL MARKET DATA</p>
        <h1>{report ? `${report.ticker} 策略监控` : "A股机构级研究终端"}</h1>
        <p className="subtitle">Real-time quant signals, financial statements, and market-wide hotspot screening.</p>
      </div>
      <div className="hero-price">
        <span>{date || "-"}</span>
        <b>{latestClose == null ? "--" : `¥${latestClose.toFixed(2)}`}</b>
        <em className={latestChange == null ? "" : latestChange >= 0 ? "up" : "down"}>{latestChange == null ? "等待最新收盘" : `${latestChange >= 0 ? "+" : ""}${latestChange.toFixed(2)}% 最近交易日`}</em>
        <strong className={`pill ${signalTone(decision)}`}>{decision}</strong>
      </div>
    </motion.section>
  );
}

function MetricStrip({ quant, report, exitSignal }) {
  const latestNetInflow = quant.latestNetInflow || quant.netInflow || "-";
  const latestNetValue = numberFrom(latestNetInflow);
  const latestFlowLabel = latestNetValue != null && latestNetValue < 0 ? "最近3日净流出" : "最近3日净流入";
  const activeExitPrice = quant.suggestedExit || quant.currentExit || quant.riskExit || "-";
  const items = [
    ["量化信号", signalLabel(quant.signal), quant.reason || "暂无量化摘要"],
    ["建议买入区间", exitSignal ? "暂停入场" : quant.entryZone || "-", exitSignal ? "当前为退场信号" : quant.entryPrice ? `T+1参考 ${quant.entryPrice}` : "等待入场评估"],
    ["当前退场价格", activeExitPrice, exitPriceHint(quant, exitSignal)],
    ["主报告建议", report?.signal || "UNKNOWN", report?.modified ? `更新 ${report.modified}` : "-"],
    ["资金流强度", quant.latestInflowRatio || quant.inflowRatio || "-", `${quant.latestFlowDate ? `截至 ${quant.latestFlowDate} ` : ""}${latestFlowLabel} ${latestNetInflow}`],
  ];
  return <section className="metrics">{items.map(([label, value, hint]) => <article key={label}><span>{label}</span><b>{value}</b><small>{hint}</small></article>)}</section>;
}

function QueryShowcase({ quant, fundamentals }) {
  const metrics = fundamentals?.metrics || {};
  const exitSignal = isExitSignal(quant.signal);
  const rows = [
    ["Signal", signalLabel(quant.signal), exitSignal ? "Entry paused" : quant.entryZone || "-", exitSignal ? quant.suggestedExit || quant.currentExit || "-" : quant.takeProfit || "-"],
    ["Revenue", formatMoney(metrics.revenue), formatChange(metrics.revenueYoY), formatMetric(metrics.peTtm, "x")],
    ["Cash Flow", formatMoney(metrics.operatingCashFlow), metrics.operatingCashFlow != null && metrics.netProfit != null ? (metrics.operatingCashFlow >= metrics.netProfit ? "High quality" : "Review") : "-", formatMetric(metrics.pb, "x")],
  ];
  return (
    <section className="showcase">
      <div className="showcase-copy">
        <h2>Search across local reports, market data, and fundamentals</h2>
        <p>Query a single stock, refresh Tushare financials, then screen the result through the existing quant model.</p>
      </div>
      <motion.div className="query-card" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }}>
        <div className="searchbar"><Search size={16} /> Find stocks with strong returns, margins, and cash flow</div>
        <p className="agent-line"><ChevronDown size={14} /> Agent: searching <code>TradingAgents</code> <Check size={14} /></p>
        <table><thead><tr><th>Item</th><th>Current</th><th>Context</th><th>Target</th></tr></thead><tbody>{rows.map((row) => <tr key={row[0]}>{row.map((cell) => <td key={cell}>{cell}</td>)}</tr>)}</tbody></table>
        <p className="agent-line"><Check size={14} /> Agent: analysis complete.</p>
      </motion.div>
    </section>
  );
}

function MarketChart({ rows, range, setRange }) {
  return (
    <motion.article className="card chart-card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <header className="card-head"><div><p className="eyebrow">MARKET SIGNAL</p><h2>资金流与价格</h2></div><RangeTabs range={range} setRange={setRange} /></header>
      <ResponsiveContainer width="100%" height={390}>
        <ComposedChart data={rows} margin={{ top: 32, right: 20, bottom: 18, left: 10 }}>
          <CartesianGrid stroke="#d9d5cc" strokeDasharray="1 12" vertical />
          <XAxis dataKey="date" tickFormatter={(v) => String(v).slice(5)} tick={{ fill: MUTED, fontSize: 11 }} axisLine={{ stroke: "#cfcac0" }} tickLine={false} />
          <YAxis yAxisId="flow" tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="price" orientation="right" tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTooltip />} />
          <Bar yAxisId="flow" dataKey="net" radius={[4, 4, 0, 0]} animationDuration={700}>
            {rows.map((row) => <Cell key={row.date} fill={(row.net || 0) >= 0 ? CHART_BLACK : CHART_GREEN} />)}
          </Bar>
          <Line yAxisId="price" type="monotone" dataKey="close" stroke={CHART_GREEN} strokeWidth={2.2} dot={false} animationDuration={900} />
        </ComposedChart>
      </ResponsiveContainer>
    </motion.article>
  );
}

function RangeTabs({ range, setRange }) {
  return <div id="chartRangeControls" className="segmented">{[[10, "10日"], [20, "20日"], [30, "30日"], [60, "60日"], [0, "全部"]].map(([value, label]) => <button key={value} className={range === value ? "active" : ""} onClick={() => setRange(value)} type="button">{label}</button>)}</div>;
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return <div className="tooltip"><b>{label}</b>{payload.map((item) => <p key={item.dataKey}>{item.name || item.dataKey}: {Number(item.value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 2 })}</p>)}</div>;
}

function StrategyPanel({ quant, exitSignal }) {
  const items = [
    ["入场参考", exitSignal ? "暂停入场" : quant.entryPrice || quant.entryZone || "-", "T+1模拟成交"],
    ["收益目标", exitSignal ? "退场优先" : quant.takeProfit || "-", exitSignal && quant.takeProfit ? `原2R目标 ${quant.takeProfit}` : "2R止盈"],
    [exitSignal ? "执行退场" : "动态退场", quant.suggestedExit || quant.currentExit || quant.riskExit || "-", exitSignal ? exitPriceHint(quant, exitSignal) : "ATR移动风控"],
  ];
  return <article className="card strategy"><p className="eyebrow">EXECUTION OBSERVER</p><h2>{signalLabel(quant.signal)}</h2><p>{quant.reason || "暂无策略判断"}</p>{items.map(([label, value, hint]) => <div className="strategy-row" key={label}><span>{label}<small>{hint}</small></span><b>{value}</b></div>)}<div className="info"><Info size={16} /> 价格仅为研究参考。实盘前必须核对公告、流动性、涨跌停和真实盘口。</div></article>;
}

function BacktestSection({ quant }) {
  const trades = quant.backtestTrades || [];
  const points = [{ equity: 100, label: "START" }];
  let equity = 100;
  trades.forEach((trade, index) => {
    const value = percentFrom(trade.return);
    if (value == null) return;
    equity *= 1 + value / 100;
    points.push({ equity: Number(equity.toFixed(2)), label: trade.exitDate || `T${index + 1}` });
  });
  const metrics = [
    ["完成交易", quant.completedTrades || trades.length || 0],
    ["胜率", formatPercentText(quant.winRate)],
    ["最大回撤", formatPercentText(quant.maxDrawdown)],
    ["盈亏因子", numberFrom(quant.profitFactor)?.toFixed(2) || "-"],
    ["平均持有", numberFrom(quant.averageHoldingDays) == null ? "-" : `${numberFrom(quant.averageHoldingDays).toFixed(1)} 天`],
  ];
  return (
    <section id="backtest" className="section-block">
      <header className="split-head"><div><p className="eyebrow">STRATEGY EVIDENCE</p><h2>单股回测与可行性证据</h2></div><span className="pill watch">{quant.evidenceGrade || "INSUFFICIENT_SAMPLE"}</span></header>
      <div className="metrics compact">{metrics.map(([label, value]) => <article key={label}><span>{label}</span><b>{value}</b></article>)}</div>
      <article className="card">
        <ResponsiveContainer width="100%" height={270}>
          <LineChart data={points} margin={{ top: 18, right: 24, bottom: 16, left: 8 }}>
            <CartesianGrid stroke="#d9d5cc" strokeDasharray="1 12" />
            <XAxis dataKey="label" tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip content={<ChartTooltip />} />
            <Line type="monotone" dataKey="equity" stroke={CHART_GREEN} strokeWidth={2.3} dot={{ r: 3, fill: CHART_BLACK }} animationDuration={900} />
          </LineChart>
        </ResponsiveContainer>
      </article>
      <DataTable rows={trades} columns={["signalDate", "entryDate", "exitDate", "entryPrice", "exitPrice", "return", "holdingDays", "status"]} empty="暂无已完成交易" />
    </section>
  );
}

function FundamentalsSection({ snapshot, loading }) {
  const metrics = snapshot?.metrics || {};
  const trendRows = (snapshot?.trends || []).map((row) => ({
    period: row.period,
    revenue: Number(row.revenue) || 0,
    netProfit: Number(row.netProfit) || 0,
    operatingCashFlow: Number(row.operatingCashFlow) || 0,
  }));
  const cards = [
    ["营业收入", formatMoney(metrics.revenue), formatChange(metrics.revenueYoY)],
    ["归母净利润", formatMoney(metrics.netProfit), formatChange(metrics.netProfitYoY)],
    ["ROE / 毛利率", `${formatMetric(metrics.roe, "%")} / ${formatMetric(metrics.grossMargin, "%")}`, `净利率 ${formatMetric(metrics.netMargin, "%")}`],
    ["经营现金流", formatMoney(metrics.operatingCashFlow), "现金质量"],
    ["资产负债率", formatMetric(metrics.debtRatio, "%"), `流动比率 ${formatMetric(metrics.currentRatio)}`],
    ["PE / PB", `${formatMetric(metrics.peTtm, "x")} / ${formatMetric(metrics.pb, "x")}`, `估值日 ${snapshot?.valuationDate || "-"}`],
  ];
  return (
    <section id="financials" className="section-block">
      <header className="split-head"><div><p className="eyebrow">FINANCIAL DATA</p><h2>财务质量与估值</h2><p>{snapshot ? `${snapshot.company?.name || snapshot.ticker} · ${snapshot.company?.industry || "行业未标注"}` : "Tushare 财务报表与每日估值"}</p></div><span className="pill">{loading ? "LOADING" : snapshot?.cached ? "CACHED" : snapshot ? "TUSHARE" : "NO DATA"}</span></header>
      <div className="metrics compact">{cards.map(([label, value, hint]) => <article key={label}><span>{label}</span><b>{value}</b><small>{hint}</small></article>)}</div>
      <div className="grid two">
        <article className="card">
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={trendRows} margin={{ top: 24, right: 24, bottom: 12, left: 10 }}>
              <CartesianGrid stroke="#d9d5cc" strokeDasharray="1 12" />
              <XAxis dataKey="period" tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="revenue" fill={CHART_BLACK} radius={[4, 4, 0, 0]} animationDuration={700} />
              <Line type="monotone" dataKey="netProfit" stroke={CHART_GREEN} strokeWidth={2} dot={false} animationDuration={900} />
              <Line type="monotone" dataKey="operatingCashFlow" stroke="#927f4a" strokeWidth={2} dot={false} animationDuration={900} />
            </ComposedChart>
          </ResponsiveContainer>
        </article>
        <article className="card prose-card"><h3>财务摘要</h3>{snapshot?.summary?.length ? snapshot.summary.map((item) => <p key={item}>{item}</p>) : <p>{loading ? "正在读取财务数据" : "暂无财务摘要"}</p>}</article>
      </div>
    </section>
  );
}

function ReportSection({ report, liveQuant, activeSection, setActiveSection }) {
  const text = activeSection === "quant" && liveQuant?.markdown ? liveQuant.markdown : report?.sections?.[activeSection] || "";
  return (
    <section id="research" className="section-block">
      <header className="split-head"><div><p className="eyebrow">RESEARCH CENTER</p><h2>研究报告中心</h2></div></header>
      <div id="tabbar" className="tabs">{SECTIONS.map(([key, label]) => <button key={key} className={activeSection === key ? "active" : ""} onClick={() => setActiveSection(key)} type="button">{label}</button>)}</div>
      <article className="markdown-card">{markdownToBlocks(text).map((block, index) => <MarkdownBlock block={block} key={`${block.type}-${index}`} />)}</article>
    </section>
  );
}

function MarkdownBlock({ block }) {
  if (block.type === "empty") return <div className="empty">{block.text}</div>;
  if (block.type === "list") return <ul>{block.items.map((item) => <li key={item}>{item}</li>)}</ul>;
  if (block.type === "h1") return <h1>{block.text}</h1>;
  if (block.type === "h2") return <h2>{block.text}</h2>;
  if (block.type === "h3") return <h3>{block.text}</h3>;
  return <p>{block.text}</p>;
}

function boardNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function boardMoney(value) {
  const n = boardNumber(value);
  return n == null ? "-" : n.toFixed(2);
}

function compactPct(value) {
  const n = boardNumber(value);
  return n == null ? "-" : `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function PersonalWorkspace({ board, status, loading, refreshing, reports, saveList, refresh, analyzeTicker }) {
  const [holdingDraft, setHoldingDraft] = useState({ ticker: "", name: "", shares: "", costPrice: "", takeProfit: "", stopLoss: "", reportId: "", thesis: "" });
  const [watchDraft, setWatchDraft] = useState({ ticker: "", name: "", theme: "", targetPrice: "", reason: "" });
  const holdings = board?.holdings || [];
  const watchlist = board?.watchlist || [];
  const candidates = board?.hotspotCandidates || [];
  const rules = board?.rules || {};
  const now = new Date().toISOString();

  function addHolding() {
    const tickerValue = holdingDraft.ticker.trim().toUpperCase();
    if (!tickerValue) return;
    saveList("holdings", [
      {
        id: `${Date.now()}`,
        ...holdingDraft,
        ticker: tickerValue,
        createdAt: now,
        updatedAt: now,
      },
      ...holdings,
    ]);
    setHoldingDraft({ ticker: "", name: "", shares: "", costPrice: "", takeProfit: "", stopLoss: "", reportId: "", thesis: "" });
  }

  function addWatch(item = watchDraft) {
    const tickerValue = item.ticker.trim().toUpperCase();
    if (!tickerValue || watchlist.some((row) => row.ticker === tickerValue)) return;
    saveList("watchlist", [
      {
        id: `${Date.now()}`,
        ticker: tickerValue,
        name: item.name || "",
        theme: item.theme || "",
        targetPrice: item.targetPrice || "",
        reason: item.reason || "",
        createdAt: now,
        updatedAt: now,
      },
      ...watchlist,
    ]);
    setWatchDraft({ ticker: "", name: "", theme: "", targetPrice: "", reason: "" });
  }

  function removeItem(listName, id) {
    saveList(listName, (board?.[listName] || []).filter((item) => item.id !== id));
  }

  function pickReport(reportId) {
    const report = reports.find((item) => item.id === reportId);
    setHoldingDraft((current) => ({
      ...current,
      reportId,
      ticker: report?.ticker || current.ticker,
      name: current.name || report?.ticker || "",
    }));
  }

  return (
    <section id="portfolio" className="content full">
      <header className="hotspot-hero">
        <div>
          <p className="eyebrow">PERSONAL RISK BOARD</p>
          <h1>我的持仓与关注股票池</h1>
          <p>把本地研报、A 股热点和手工仓位放在同一个监控面板里；价格触线只做提醒，不连接券商。</p>
        </div>
        <div className="hotspot-actions">
          <button className="secondary small" onClick={refresh} disabled={refreshing || loading || !holdings.length} type="button"><Bell size={15} /> {refreshing ? "刷新中" : "刷新持仓监控"}</button>
          <button className="secondary small" onClick={() => window.location.hash = "#hotspots"} type="button"><Flame size={15} /> 查看热点雷达</button>
        </div>
      </header>
      <AgentStatus status={status} />
      <div className="rules-grid">
        <article className="card rule-card"><p className="eyebrow">FOCUS</p><h2>关注方向</h2><p>{(rules.focus || []).slice(0, 16).join(" / ") || "-"}</p></article>
        <article className="card rule-card"><p className="eyebrow">AVOID</p><h2>排除方向</h2><p>{(rules.avoid || []).join(" / ") || "-"}</p></article>
        <article className="card rule-card"><p className="eyebrow">REMOTE</p><h2>小龙虾提醒</h2><p>{board?.notification?.enabled ? "已启用远程提醒" : "当前为本地看板，已预留远程推送字段"}</p></article>
      </div>
      <div className="grid personal-grid">
        <article className="card">
          <header className="card-head"><div><p className="eyebrow">HOLDINGS</p><h2>个人持仓</h2></div><span className="pill">{holdings.length} POSITIONS</span></header>
          <div className="compact-form holdings-form">
            <select value={holdingDraft.reportId} onChange={(event) => pickReport(event.target.value)}>
              <option value="">选择本地研报绑定</option>
              {reports.map((report) => <option key={report.id} value={report.id}>{report.ticker} · {report.analysisDate}</option>)}
            </select>
            <input placeholder="代码 000966.SZ" value={holdingDraft.ticker} onChange={(event) => setHoldingDraft({ ...holdingDraft, ticker: event.target.value.toUpperCase() })} />
            <input placeholder="名称/备注" value={holdingDraft.name} onChange={(event) => setHoldingDraft({ ...holdingDraft, name: event.target.value })} />
            <input placeholder="股数" inputMode="decimal" value={holdingDraft.shares} onChange={(event) => setHoldingDraft({ ...holdingDraft, shares: event.target.value })} />
            <input placeholder="成本价" inputMode="decimal" value={holdingDraft.costPrice} onChange={(event) => setHoldingDraft({ ...holdingDraft, costPrice: event.target.value })} />
            <input placeholder="止盈线" inputMode="decimal" value={holdingDraft.takeProfit} onChange={(event) => setHoldingDraft({ ...holdingDraft, takeProfit: event.target.value })} />
            <input placeholder="止损线" inputMode="decimal" value={holdingDraft.stopLoss} onChange={(event) => setHoldingDraft({ ...holdingDraft, stopLoss: event.target.value })} />
            <button className="primary small" type="button" onClick={addHolding} disabled={loading}><Plus size={15} /> 添加持仓</button>
          </div>
          <HoldingTable rows={holdings} remove={(id) => removeItem("holdings", id)} analyzeTicker={analyzeTicker} />
        </article>
        <article className="card">
          <header className="card-head"><div><p className="eyebrow">WATCHLIST</p><h2>关注股票池</h2></div><span className="pill watch">{board?.hotspotDate || "NO HOTSPOT"}</span></header>
          <div className="compact-form watch-form">
            <input placeholder="代码" value={watchDraft.ticker} onChange={(event) => setWatchDraft({ ...watchDraft, ticker: event.target.value.toUpperCase() })} />
            <input placeholder="名称" value={watchDraft.name} onChange={(event) => setWatchDraft({ ...watchDraft, name: event.target.value })} />
            <input placeholder="方向/板块" value={watchDraft.theme} onChange={(event) => setWatchDraft({ ...watchDraft, theme: event.target.value })} />
            <input placeholder="目标观察价" inputMode="decimal" value={watchDraft.targetPrice} onChange={(event) => setWatchDraft({ ...watchDraft, targetPrice: event.target.value })} />
            <button className="primary small" type="button" onClick={() => addWatch()} disabled={loading}><Plus size={15} /> 加入股票池</button>
          </div>
          <WatchTable rows={watchlist} remove={(id) => removeItem("watchlist", id)} analyzeTicker={analyzeTicker} />
        </article>
      </div>
      <section className="section-block">
        <header className="split-head"><div><p className="eyebrow">HOTSPOT CANDIDATES</p><h2>热点候选加入关注池</h2><p>按未来方向关键词、排除行业和小盘过滤后的本地热点结果。</p></div><span className="pill">{candidates.length} CANDIDATES</span></header>
        <CandidateTable rows={candidates} addWatch={addWatch} analyzeTicker={analyzeTicker} />
      </section>
    </section>
  );
}

function HoldingTable({ rows, remove, analyzeTicker }) {
  if (!rows.length) return <div className="empty">还没有手工持仓，先从已有研报或股票代码添加。</div>;
  return (
    <div className="table-card board-table">
      <table>
        <thead><tr><th>股票</th><th>仓位</th><th>监控价</th><th>盈亏</th><th>止盈/止损</th><th>报告</th><th>提醒</th><th>操作</th></tr></thead>
        <tbody>{rows.map((row) => {
          const monitor = row.monitor || {};
          const alerts = row.alerts || [];
          return (
            <tr key={row.id}>
              <td><b>{row.name || row.ticker}</b><small>{row.ticker}</small></td>
              <td>{boardMoney(row.shares)}<small>成本 {boardMoney(row.costPrice)}</small></td>
              <td>{boardMoney(monitor.latestPrice)}<small>{monitor.latestDate || monitor.refreshedAt || "-"}</small></td>
              <td className={boardNumber(row.pnlPct) >= 0 ? "up-text" : "down-text"}>{boardMoney(row.pnl)}<small>{compactPct(row.pnlPct)}</small></td>
              <td>{boardMoney(row.takeProfit)}<small>{boardMoney(row.stopLoss)}</small></td>
              <td><span className={`pill tiny ${row.hasReport ? "positive" : "watch"}`}>{row.hasReport ? "已绑定" : "缺研报"}</span></td>
              <td><AlertList alerts={alerts} /></td>
              <td><div className="row-actions"><button className="link-btn" type="button" onClick={() => analyzeTicker(row.ticker)}>分析</button><button className="icon-btn" type="button" onClick={() => remove(row.id)}><Trash2 size={14} /></button></div></td>
            </tr>
          );
        })}</tbody>
      </table>
    </div>
  );
}

function AlertList({ alerts }) {
  if (!alerts?.length) return <span className="pill tiny positive">正常</span>;
  return <div className="alert-list">{alerts.map((alert) => <span key={alert.code} className={`pill tiny ${alert.level === "danger" ? "negative" : alert.level === "success" ? "positive" : "watch"}`}>{alert.code}</span>)}</div>;
}

function WatchTable({ rows, remove, analyzeTicker }) {
  if (!rows.length) return <div className="empty">还没有关注股票，先手工添加或从热点候选加入。</div>;
  return (
    <div className="table-card board-table">
      <table>
        <thead><tr><th>股票</th><th>方向</th><th>目标价</th><th>热点</th><th>报告</th><th>操作</th></tr></thead>
        <tbody>{rows.map((row) => (
          <tr key={row.id}>
            <td><b>{row.name || row.ticker}</b><small>{row.ticker}</small></td>
            <td>{row.theme || "-"}<small>{row.reason || row.note || "-"}</small></td>
            <td>{boardMoney(row.targetPrice)}</td>
            <td>{row.hotspot ? Number(row.hotspotScore || 0).toFixed(1) : "-"}<small>{row.hotspotDate || "-"}</small></td>
            <td><span className={`pill tiny ${row.hasReport ? "positive" : "watch"}`}>{row.hasReport ? "已有" : "未分析"}</span></td>
            <td><div className="row-actions"><button className="link-btn" type="button" onClick={() => analyzeTicker(row.ticker)}>分析</button><button className="icon-btn" type="button" onClick={() => remove(row.id)}><Trash2 size={14} /></button></div></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function CandidateTable({ rows, addWatch, analyzeTicker }) {
  if (!rows.length) return <div className="empty">当前热点结果里没有命中你设定方向的候选，先生成最新热点雷达。</div>;
  return (
    <div className="table-card board-table">
      <table>
        <thead><tr><th>股票</th><th>方向</th><th>评分</th><th>资金流</th><th>放量</th><th>操作</th></tr></thead>
        <tbody>{rows.map((row) => (
          <tr key={row.ticker}>
            <td><b>{row.name}</b><small>{row.ticker}</small></td>
            <td>{row.theme || "-"}</td>
            <td><b>{Number(row.stockScore || 0).toFixed(1)}</b></td>
            <td>{hotspotPercent(row.netFlowRatio, true)}<small>大单 {hotspotPercent(row.bigOrderRatio, true)}</small></td>
            <td>{Number(row.amountRatio20 || 0).toFixed(2)}x</td>
            <td><div className="row-actions"><button className="link-btn" type="button" onClick={() => addWatch({ ticker: row.ticker, name: row.name, theme: row.theme, reason: "hotspot candidate" })}><Star size={13} /> 关注</button><button className="link-btn" type="button" onClick={() => analyzeTicker(row.ticker)}>分析</button></div></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function HotspotWorkspace({ hotspot, setHotspot, selectDate, runScan, exportHtml, analyzeTicker }) {
  const summary = hotspot.data?.summary || {};
  const rows = useMemo(() => {
    const source = [...(hotspot.data?.[hotspot.view] || [])];
    return source.sort((a, b) => Number(b[hotspot.sort] ?? -Infinity) - Number(a[hotspot.sort] ?? -Infinity));
  }, [hotspot.data, hotspot.view, hotspot.sort]);
  return (
    <section id="hotspots" className="content full">
      <header className="hotspot-hero">
        <div><p className="eyebrow">MARKET-WIDE RADAR</p><h1>A股日终热点雷达</h1><p>全市场批量资金流、大宗交易、放量与板块共振筛选</p></div>
        <div className="hotspot-actions">
          <DatePicker hotspot={hotspot} setHotspot={setHotspot} selectDate={selectDate} />
          <button className="primary small" onClick={runScan} disabled={hotspot.running} type="button"><RefreshCw size={15} /> {hotspot.running ? "生成中" : "生成所选日期热点榜"}</button>
          <button className="secondary small" onClick={exportHtml} disabled={!hotspot.data?.tradeDate} type="button"><Download size={15} /> 导出交互 HTML</button>
        </div>
      </header>
      <AgentStatus status={hotspot.job} />
      <div className="metrics compact">
        <article><span>有效股票池</span><b>{summary.eligibleStocks ?? "-"}</b><small>沪深 · 已过滤流动性</small></article>
        <article><span>触发任一信号</span><b>{summary.triggeredStocks ?? "-"}</b><small>资金流 / 大宗 / 放量</small></article>
        <article><span>资金流覆盖率</span><b>{summary.moneyflowCoverage == null ? "-" : `${(summary.moneyflowCoverage * 100).toFixed(2)}%`}</b><small>moneyflow 数据完整度</small></article>
        <article><span>大宗交易股票</span><b>{summary.blockTradeStocks ?? "-"}</b><small>当日存在成交记录</small></article>
      </div>
      <div className="grid hotspot-grid">
        <article className="card"><header className="card-head"><div><p className="eyebrow">SECTOR RANKING</p><h2>板块共振 Top 10</h2></div></header><SectorTable rows={hotspot.data?.sectors || []} /></article>
        <article className="card">
          <header className="card-head"><div><p className="eyebrow">STOCK RANKING</p><h2>热点个股 Top 30</h2></div><HotspotTabs view={hotspot.view} setView={(view) => setHotspot((current) => ({ ...current, view }))} /></header>
          <div className="sortline"><label>排序</label><select id="hotspotSort" value={hotspot.sort} onChange={(event) => setHotspot((current) => ({ ...current, sort: event.target.value }))}><option value="stock_score">综合评分</option><option value="net_flow_ratio">净流入比例</option><option value="big_elg_flow_ratio">大单比例</option><option value="block_vwap_premium">大宗溢价</option><option value="amount_ratio_20">成交额放大</option></select></div>
          <StockTable rows={rows} analyzeTicker={analyzeTicker} />
        </article>
      </div>
      <div className="note wide"><Info size={17} /> 热点不等于买点。榜单只负责缩小研究范围；入场价格、风险退出与基本面仍由单股模块继续验证。</div>
    </section>
  );
}

function DatePicker({ hotspot, setHotspot, selectDate }) {
  const [open, setOpen] = useState(false);
  const month = hotspot.month || new Date();
  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  const dayCount = new Date(year, monthIndex + 1, 0).getDate();
  const offset = (new Date(year, monthIndex, 1).getDay() + 6) % 7;
  const available = new Set(hotspot.availableDates);
  const scanned = new Set(hotspot.scannedDates);
  const trading = new Set(hotspot.tradingDates);
  return (
    <div className="date-picker">
      <button className="secondary small" type="button" onClick={() => setOpen(!open)}><CalendarDays size={15} /> {hotspot.selectedDate ? String(hotspot.selectedDate).replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3") : "选择交易日"}</button>
      <AnimatePresence>
        {open && (
          <motion.div className="calendar" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
            <div className="calendar-head"><button onClick={() => setHotspot((current) => ({ ...current, month: new Date(year, monthIndex - 1, 1) }))} type="button">‹</button><b>{year}年 {monthIndex + 1}月</b><button onClick={() => setHotspot((current) => ({ ...current, month: new Date(year, monthIndex + 1, 1) }))} type="button">›</button></div>
            <div className="week">{["一", "二", "三", "四", "五", "六", "日"].map((day) => <span key={day}>{day}</span>)}</div>
            <div className="days">{Array.from({ length: dayCount }, (_, index) => {
              const day = index + 1;
              const key = `${year}${String(monthIndex + 1).padStart(2, "0")}${String(day).padStart(2, "0")}`;
              const selectable = available.has(key) || scanned.has(key) || trading.has(key) || key === hotspot.latestTradeDate;
              const cls = [scanned.has(key) ? "scanned" : "", available.has(key) ? "available" : "", trading.has(key) ? "trading" : "", key === hotspot.selectedDate ? "selected" : ""].filter(Boolean).join(" ");
              return <button key={key} className={cls} style={index === 0 ? { gridColumnStart: offset + 1 } : undefined} disabled={!selectable} onClick={() => { setOpen(false); selectDate(key); }} type="button">{day}</button>;
            })}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function HotspotTabs({ view, setView }) {
  return <div id="hotspotViewTabs" className="segmented">{[["stocks", "综合"], ["moneyflowTop", "资金流"], ["blockTrades", "大宗"]].map(([key, label]) => <button key={key} className={view === key ? "active" : ""} onClick={() => setView(key)} type="button">{label}</button>)}</div>;
}

function SectorTable({ rows }) {
  if (!rows.length) return <div className="empty">暂无板块结果</div>;
  return <table><thead><tr><th>#</th><th>板块</th><th>评分</th><th>触发/总数</th><th>平均净流入</th><th>放量</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.sector_name}-${index}`}><td>{index + 1}</td><td>{row.sector_name || "未分类"}</td><td><b>{Number(row.sector_score || 0).toFixed(1)}</b></td><td>{Number(row.triggered_stock_count || 0)}/{Number(row.stock_count || 0)}</td><td>{hotspotPercent(row.avg_net_flow_ratio, true)}</td><td>{Number(row.avg_amount_ratio_20 || 0).toFixed(2)}x</td></tr>)}</tbody></table>;
}

function StockTable({ rows, analyzeTicker }) {
  if (!rows.length) return <div className="empty">当前榜单没有符合条件的股票</div>;
  return <table><thead><tr><th>股票</th><th>行业</th><th>评分</th><th>涨跌</th><th>净流入</th><th>大单</th><th>大宗溢价</th><th>放量</th><th>操作</th></tr></thead><tbody>{rows.map((row) => <tr key={row.ts_code}><td><b>{row.name || row.ts_code}</b><small>{row.ts_code}</small></td><td>{row.sector_level_1 || "未分类"}</td><td><b>{Number(row.stock_score || 0).toFixed(1)}</b></td><td>{hotspotChange(row.pct_chg)}</td><td>{hotspotPercent(row.net_flow_ratio, true)}</td><td>{hotspotPercent(row.big_elg_flow_ratio, true)}</td><td>{hotspotPercent(row.block_vwap_premium, true)}</td><td>{Number(row.amount_ratio_20 || 0).toFixed(2)}x</td><td><button className="link-btn" onClick={() => analyzeTicker(row.ts_code)} type="button">单股分析</button></td></tr>)}</tbody></table>;
}

function hotspotPercent(value, signed = false) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return `${signed && n > 0 ? "+" : ""}${(n * 100).toFixed(2)}%`;
}

function hotspotChange(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function DataTable({ rows, columns, empty }) {
  if (!rows?.length) return <div className="empty">{empty}</div>;
  return <article className="card table-card"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{String(row[column] ?? "-")}</td>)}</tr>)}</tbody></table></article>;
}

createRoot(document.getElementById("root")).render(<App />);
