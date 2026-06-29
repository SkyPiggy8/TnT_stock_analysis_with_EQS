from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any


def render_hotspot_export(payload: dict[str, Any]) -> str:
    """Render one self-contained, backend-free interactive hotspot report."""

    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    trade_date = str(payload.get("tradeDate") or "-")
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>A股热点雷达 - {trade_date}</title>
  <style>
    :root{{--bg:#0b0e11;--panel:#151a21;--line:#2b3139;--text:#eaecef;--muted:#848e9c;--yellow:#f0b90b;--red:#f6465d;--green:#0ecb81}}
    *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
    main{{width:min(1440px,calc(100% - 32px));margin:auto;padding:30px 0 48px}} h1,h2,p{{margin:0}} h1{{font-size:26px}} h2{{font-size:16px}}
    .muted{{color:var(--muted)}} .top{{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:20px}} .brand{{color:var(--yellow);font-weight:800;letter-spacing:.08em}}
    .summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}} .card,.panel{{border:1px solid var(--line);border-radius:10px;background:var(--panel)}}
    .card{{padding:16px}} .card span{{display:block;color:var(--muted);font-size:12px}} .card strong{{display:block;margin-top:8px;font-size:24px}}
    .grid{{display:grid;grid-template-columns:minmax(300px,.7fr) minmax(620px,1.3fr);gap:14px}} .panel{{min-width:0;padding:16px}} .panel-head{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}}
    .tabs{{display:flex;gap:4px}} button,select,input{{border:1px solid var(--line);border-radius:6px;background:#0f1318;color:var(--text)}} button{{padding:7px 10px;cursor:pointer}} button.active{{border-color:var(--yellow);background:var(--yellow);color:#181a20;font-weight:800}}
    .toolbar{{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;margin-bottom:10px}} input{{min-width:190px;padding:8px 10px}} select{{padding:8px}}
    .table-wrap{{max-height:68vh;overflow:auto}} table{{width:100%;border-collapse:collapse;font-size:12px}} th,td{{padding:9px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}} th{{position:sticky;top:0;background:#10151b;color:var(--muted)}}
    .score{{color:var(--yellow);font-weight:800}} .positive{{color:var(--red)}} .negative{{color:var(--green)}} .sector-link{{border:0;background:transparent;color:var(--text);padding:0;text-align:left}} .sector-link:hover{{color:var(--yellow)}}
    .empty{{padding:28px!important;color:var(--muted);text-align:center}} footer{{margin-top:18px;color:var(--muted);font-size:12px}}
    @media(max-width:900px){{main{{width:min(100% - 20px,1440px);padding-top:18px}}.top{{align-items:flex-start;flex-direction:column}}.summary{{grid-template-columns:1fr 1fr}}.grid{{grid-template-columns:1fr}}.toolbar{{justify-content:flex-start}}}}
    @media(max-width:520px){{.summary{{grid-template-columns:1fr}}.panel-head{{align-items:flex-start;flex-direction:column}}}}
  </style>
</head>
<body>
<main>
  <header class="top"><div><div class="brand">MARKET-WIDE RADAR</div><h1>A股日终热点雷达</h1><p class="muted">交易日 <span id="tradeDate">-</span> · 数据已嵌入本文件</p></div><div class="muted">导出时间：{generated_at}</div></header>
  <section class="summary"><article class="card"><span>有效股票池</span><strong id="eligible">-</strong></article><article class="card"><span>触发任一信号</span><strong id="triggered">-</strong></article><article class="card"><span>资金流覆盖率</span><strong id="coverage">-</strong></article><article class="card"><span>大宗交易股票</span><strong id="blocks">-</strong></article></section>
  <section class="grid">
    <article class="panel"><div class="panel-head"><div><h2>板块共振 Top 10</h2><p class="muted">点击板块可筛选个股</p></div><button id="clearSector" type="button">清除筛选</button></div><div class="table-wrap"><table><thead><tr><th>#</th><th>板块</th><th>评分</th><th>触发/总数</th><th>净流入</th><th>放量</th></tr></thead><tbody id="sectorBody"></tbody></table></div></article>
    <article class="panel"><div class="panel-head"><div><h2>热点个股</h2><p id="filterLabel" class="muted">综合榜</p></div><div id="tabs" class="tabs"><button class="active" data-view="stocks">综合</button><button data-view="moneyflowTop">资金流</button><button data-view="blockTrades">大宗</button></div></div><div class="toolbar"><input id="search" placeholder="搜索代码、名称或行业"><select id="sort"><option value="stock_score">综合评分</option><option value="net_flow_ratio">净流入比例</option><option value="big_elg_flow_ratio">大单比例</option><option value="block_vwap_premium">大宗溢价</option><option value="amount_ratio_20">成交额放量</option></select></div><div class="table-wrap"><table><thead><tr><th>股票</th><th>行业</th><th>评分</th><th>涨跌</th><th>净流入</th><th>大单</th><th>大宗溢价</th><th>放量</th></tr></thead><tbody id="stockBody"></tbody></table></div></article>
  </section>
  <footer>本报告仅用于收盘后研究筛选，不构成投资建议，不会产生真实交易订单。</footer>
</main>
<script>
  const bytes=Uint8Array.from(atob("{encoded}"),c=>c.charCodeAt(0));
  const DATA=JSON.parse(new TextDecoder().decode(bytes));
  let view="stocks", sector="";
  const $=id=>document.getElementById(id);
  const esc=value=>String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
  const pct=(value,signed=false)=>{{const n=Number(value);return Number.isFinite(n)?`${{signed&&n>0?"+":""}}${{(n*100).toFixed(2)}}%`:"-"}};
  const change=value=>{{const n=Number(value);return Number.isFinite(n)?`${{n>0?"+":""}}${{n.toFixed(2)}}%`:"-"}};
  const cls=value=>{{const n=Number(value);return !Number.isFinite(n)||n===0?"":n>0?"positive":"negative"}};
  const summary=DATA.summary||{{}};
  $("tradeDate").textContent=DATA.tradeDate||"-"; $("eligible").textContent=summary.eligibleStocks??"-"; $("triggered").textContent=summary.triggeredStocks??"-"; $("coverage").textContent=summary.moneyflowCoverage==null?"-":pct(summary.moneyflowCoverage); $("blocks").textContent=summary.blockTradeStocks??"-";
  function renderSectors(){{const rows=DATA.sectors||[];$("sectorBody").innerHTML=rows.length?rows.map((row,i)=>`<tr><td>${{i+1}}</td><td><button class="sector-link" data-sector="${{esc(row.sector_name)}}">${{esc(row.sector_name)}}</button></td><td class="score">${{Number(row.sector_score||0).toFixed(1)}}</td><td>${{row.triggered_stock_count??0}} / ${{row.stock_count??0}}</td><td class="${{cls(row.avg_net_flow_ratio)}}">${{pct(row.avg_net_flow_ratio,true)}}</td><td>${{Number(row.avg_amount_ratio_20||0).toFixed(2)}}x</td></tr>`).join(""):`<tr><td colspan="6" class="empty">暂无数据</td></tr>`}}
  function renderStocks(){{const query=$("search").value.trim().toLowerCase(),sort=$("sort").value;const rows=[...(DATA[view]||[])].filter(row=>{{const text=`${{row.ts_code||""}} ${{row.name||""}} ${{row.sector_level_1||""}}`.toLowerCase();return(!sector||row.sector_level_1===sector)&&(!query||text.includes(query))}}).sort((a,b)=>Number(b[sort]||0)-Number(a[sort]||0));$("filterLabel").textContent=`${{sector?sector+" · ":""}}${{view==="stocks"?"综合榜":view==="moneyflowTop"?"资金流榜":"大宗交易榜"}} · ${{rows.length}}只`;$("stockBody").innerHTML=rows.length?rows.map(row=>`<tr><td><strong>${{esc(row.name||"-")}}</strong><br><span class="muted">${{esc(row.ts_code||"")}}</span></td><td>${{esc(row.sector_level_1||"-")}}</td><td class="score">${{Number(row.stock_score||0).toFixed(1)}}</td><td class="${{cls(row.pct_chg)}}">${{change(row.pct_chg)}}</td><td class="${{cls(row.net_flow_ratio)}}">${{pct(row.net_flow_ratio,true)}}</td><td class="${{cls(row.big_elg_flow_ratio)}}">${{pct(row.big_elg_flow_ratio,true)}}</td><td class="${{cls(row.block_vwap_premium)}}">${{pct(row.block_vwap_premium,true)}}</td><td>${{Number(row.amount_ratio_20||0).toFixed(2)}}x</td></tr>`).join(""):`<tr><td colspan="8" class="empty">无匹配数据</td></tr>`}}
  $("tabs").addEventListener("click",event=>{{const button=event.target.closest("button[data-view]");if(!button)return;view=button.dataset.view;document.querySelectorAll("#tabs button").forEach(item=>item.classList.toggle("active",item===button));renderStocks()}});
  $("sectorBody").addEventListener("click",event=>{{const button=event.target.closest("button[data-sector]");if(!button)return;sector=button.dataset.sector;renderStocks()}});
  $("clearSector").addEventListener("click",()=>{{sector="";renderStocks()}}); $("search").addEventListener("input",renderStocks); $("sort").addEventListener("change",renderStocks);
  renderSectors();renderStocks();
</script>
</body>
</html>"""
