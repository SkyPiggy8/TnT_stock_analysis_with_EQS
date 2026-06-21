<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="./assets/wechat.png" target="_blank"><img alt="WeChat" src="https://img.shields.io/badge/WeChat-TauricResearch-brightgreen?logo=wechat&logoColor=white"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <br>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/Join_GitHub_Community-TauricResearch-14C290?logo=discourse"/></a>
</div>

<div align="center">
  <!-- Keep these links. Translations will automatically update with the README. -->
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=de">Deutsch</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=es">Español</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=fr">français</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ja">日本語</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ko">한국어</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=pt">Português</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ru">Русский</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=zh">中文</a>
</div>

---

# TnT_LuLuPig：面向 A 股增强的 TradingAgents

## 项目来源与引用说明

本仓库 [SkyPiggy8/TnT_LuLuPig](https://github.com/SkyPiggy8/TnT_LuLuPig) 基于开源项目 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 进行二次开发。TradingAgents 原项目提出并实现了基于多智能体协作的金融交易研究框架；本仓库保留其核心架构，并针对中国 A 股的数据获取、分析流程和本地使用体验进行了扩展。

感谢 TradingAgents 原作者 Yijia Xiao、Edward Sun、Di Luo 和 Wei Wang 及其社区贡献者。本仓库不是 TauricResearch 发布的官方版本；新增功能、适配代码和相关问题由本仓库维护。使用或引用本仓库时，也请同时注明 TradingAgents 上游项目，并参考本文末尾的论文引用信息。

### 本仓库的主要改进

- 新增 Tushare 与 AKShare A 股行情适配，支持按配置切换数据源和故障回退。
- 新增基于 AKShare 的财联社、同花顺中文资讯接入，并按股票代码、名称和关键词筛选市场新闻。
- 新增 A 股财务报表、估值指标和财务趋势快照，补充原项目对中国市场基本面数据的支持。
- 新增基于资金流的 A 股量化策略报告，并可结合新闻和基本面变化调整信号判断。
- 新增本地 Web 看板，可查看历史分析报告、分析师分项、数据获取日志、财务趋势、估值指标和量化策略。
- 增强环境变量配置、无数据场景处理、行情数据校验和运行稳定性，并补充相关测试。

上游框架的详细介绍、论文与原始设计保留在下文中。

## News
- [2026-05] **TradingAgents v0.2.5** released with the grounded Sentiment Analyst, GPT-5.5 etc. model coverage, Qwen/GLM/MiniMax dual-region support, `TRADINGAGENTS_*` env-var configurability with API-key auto-detection, remote Ollama support, non-US alpha benchmarks, and ticker path-traversal hardening. See [CHANGELOG.md](CHANGELOG.md) for the full list.
- [2026-04] **TradingAgents v0.2.4** released with structured-output agents (Research Manager, Trader, Portfolio Manager), LangGraph checkpoint resume, persistent decision log, DeepSeek/Qwen/GLM/Azure provider support, Docker, and a Windows UTF-8 encoding fix.
- [2026-03] **TradingAgents v0.2.3** released with multi-language support, GPT-5.4 family models, unified model catalog, backtesting date fidelity, and proxy support.
- [2026-03] **TradingAgents v0.2.2** released with GPT-5.4/Gemini 3.1/Claude 4.6 model coverage, five-tier rating scale, OpenAI Responses API, Anthropic effort control, and cross-platform stability.
- [2026-02] **TradingAgents v0.2.0** released with multi-provider LLM support (GPT-5.x, Gemini 3.x, Claude 4.x, Grok 4.x) and improved system architecture.
- [2026-01] **Trading-R1** [Technical Report](https://arxiv.org/abs/2509.11420) released, with [Terminal](https://github.com/TauricResearch/Trading-R1) expected to land soon.

<div align="center">
<a href="https://www.star-history.com/#TauricResearch/TradingAgents&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" />
   <img alt="TradingAgents Star History" src="https://api.star-history.com/svg?repos=TauricResearch/TradingAgents&type=Date" style="width: 80%; height: auto;" />
 </picture>
</a>
</div>

> 🎉 **TradingAgents** officially released! We have received numerous inquiries about the work, and we would like to express our thanks for the enthusiasm in our community.
>
> So we decided to fully open-source the framework. Looking forward to building impactful projects with you!

<div align="center">

🚀 [TradingAgents](#tradingagents-framework) | ⚡ [Installation & CLI](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

## TradingAgents Framework

TradingAgents is a multi-agent trading framework that mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents: from fundamental analysts, sentiment experts, and technical analysts, to trader, risk management team, the platform collaboratively evaluates market conditions and informs trading decisions. Moreover, these agents engage in dynamic discussions to pinpoint the optimal strategy.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents framework is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. [It is not intended as financial, investment, or trading advice.](https://tauric.ai/disclaimer/)

Our framework decomposes complex trading tasks into specialized roles.

### Analyst Team
- Fundamentals Analyst: Evaluates company financials and performance metrics, identifying intrinsic values and potential red flags.
- Sentiment Analyst: Aggregates news headlines and market events into a single sentiment read to gauge short-term market mood.
- News Analyst: Monitors global news and macroeconomic indicators, interpreting the impact of events on market conditions.
- Technical Analyst: Utilizes technical indicators (like MACD and RSI) to detect trading patterns and forecast price movements.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Researcher Team
- Comprises both bullish and bearish researchers who critically assess the insights provided by the Analyst Team. Through structured debates, they balance potential gains against inherent risks.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Trader Agent
- Composes reports from the analysts and researchers to make informed trading decisions, determining the timing and magnitude of trades.

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Risk Management and Portfolio Manager
- Continuously evaluates portfolio risk by assessing market volatility, liquidity, and other risk factors. The risk management team evaluates and adjusts trading strategies, providing assessment reports to the Portfolio Manager for final decision.
- The Portfolio Manager approves/rejects the transaction proposal. If approved, the order will be sent to the simulated exchange and executed.

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## Installation and CLI

### 支持的平台

本仓库支持以下 64 位平台：

- Apple Silicon（M1/M2/M3/M4 等 ARM64 芯片）的 macOS
- Windows 10/11（PowerShell）
- Linux（以下命令以 Ubuntu/Debian 为例，其他发行版请使用对应的包管理器）

需要 Git 和 Python 3.10 或更高版本。所有平台均建议使用独立虚拟环境，避免依赖污染系统 Python。

### macOS ARM64（Apple Silicon）

以下命令使用 ARM 原生 Homebrew。Homebrew 在 Apple Silicon 上的默认目录应为 `/opt/homebrew`；不要在 Rosetta/x86_64 终端中混装 Python 依赖。

```bash
# 如尚未安装命令行开发工具
xcode-select --install

# 安装 ARM 原生 Git 和 Python（需要先安装 Homebrew）
brew install git python

git clone https://github.com/SkyPiggy8/TnT_LuLuPig.git
cd TnT_LuLuPig

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

可用下面的命令确认当前终端和 Python 都运行在 ARM64 环境：

```bash
uname -m
python -c "import platform; print(platform.machine())"
```

两条命令都应输出 `arm64`。

### Windows 10/11（PowerShell）

先安装 [Git for Windows](https://git-scm.com/download/win) 和 [Python](https://www.python.org/downloads/windows/)，安装 Python 时勾选 **Add Python to PATH**。然后在 PowerShell 中运行：

```powershell
git clone https://github.com/SkyPiggy8/TnT_LuLuPig.git
Set-Location TnT_LuLuPig

py -3 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

`Set-ExecutionPolicy -Scope Process` 只影响当前 PowerShell 会话，不修改系统级执行策略。

### Linux（Ubuntu/Debian）

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

git clone https://github.com/SkyPiggy8/TnT_LuLuPig.git
cd TnT_LuLuPig

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

### 配置 API 密钥

在仓库根目录创建 `.env` 文件，并仅填写实际使用的服务。至少需要配置一个 LLM 服务商；分析 A 股时建议同时配置 Tushare：

```dotenv
OPENAI_API_KEY=your_openai_api_key
TUSHARE_TOKEN=your_tushare_token
```

`.env` 已被 `.gitignore` 忽略。不要将真实 API 密钥提交到 GitHub。

### Docker

Alternatively, run with Docker:
```bash
docker compose run --rm tradingagents
```

Docker 启动前同样需要在仓库根目录创建 `.env`。Docker Desktop 可用于 Apple Silicon macOS 和 Windows；Linux 需要 Docker Engine 与 Compose 插件。

For local models with Ollama:
```bash
docker compose --profile ollama run --rm tradingagents-ollama
```

### Required APIs

TradingAgents supports multiple LLM providers. Set the API key for your chosen provider:

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export DEEPSEEK_API_KEY=...        # DeepSeek
export DASHSCOPE_API_KEY=...       # Qwen — International (dashscope-intl.aliyuncs.com)
export DASHSCOPE_CN_API_KEY=...    # Qwen — China (dashscope.aliyuncs.com)
export ZHIPU_API_KEY=...           # GLM via Z.AI (international)
export ZHIPU_CN_API_KEY=...        # GLM via BigModel (China, open.bigmodel.cn)
export MINIMAX_API_KEY=...         # MiniMax — Global (api.minimax.io, M3 1M ctx + M2.x)
export MINIMAX_CN_API_KEY=...      # MiniMax — China (api.minimaxi.com, M3 1M ctx + M2.x)
export OPENROUTER_API_KEY=...      # OpenRouter
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
```

For enterprise providers (e.g. Azure OpenAI, AWS Bedrock), copy `.env.enterprise.example` to `.env.enterprise` and fill in your credentials.

For `MiniMax-M3`, choose the region that issued the key: `Global` uses
`MINIMAX_API_KEY` with `api.minimax.io`, while `China` uses
`MINIMAX_CN_API_KEY` with `api.minimaxi.com`. The two account systems and keys
are not interchangeable. `MiniMax-M3` is available in both the quick- and
deep-thinking model menus.

For local models, configure Ollama with `llm_provider: "ollama"`. The default endpoint is `http://localhost:11434/v1`; set `OLLAMA_BASE_URL` to point at a remote `ollama-serve`. Pull models with `ollama pull <name>`, and pick "Custom model ID" in the CLI for any model not listed by default.

You may place the selected keys in the `.env` file created during installation. The application loads it automatically without overriding variables already set in the shell.

### CLI Usage

Launch the interactive CLI:
```bash
tradingagents          # installed command
python -m cli.main     # alternative: run directly from source
```
You will see a screen where you can select your desired tickers, analysis date, LLM provider, research depth, and more.

### Markets and tickers

TradingAgents works with any market Yahoo Finance covers, using the exchange-suffixed ticker. Company identity and the alpha benchmark resolve automatically per market.

- US: `AAPL`, `SPY`
- Hong Kong: `0700.HK` · Tokyo: `7203.T` · London: `AZN.L`
- India: `RELIANCE.NS`, `.BO` · Canada: `.TO` · Australia: `.AX`
- China A-shares: Shanghai `.SS`, Shenzhen `.SZ` (e.g. `600519.SS` for Kweichow Moutai)
- Crypto: `BTC-USD`, `ETH-USD`

### Data vendors

For China A-shares, TradingAgents prioritizes Tushare for daily OHLCV data and technical indicators, with AKShare available as a no-key backup. Yahoo Finance remains in the fallback chain for non-A-share symbols and limited international news context.

```bash
export TUSHARE_TOKEN=your_tushare_token
export TRADINGAGENTS_CORE_STOCK_VENDOR=tushare,akshare
export TRADINGAGENTS_TECHNICAL_INDICATORS_VENDOR=tushare,akshare
export TRADINGAGENTS_FUNDAMENTAL_DATA_VENDOR=tushare,yfinance
```

For A-share news, the Chinese-news adapter pulls from 财联社 and 同花顺 through AKShare, then falls back to yfinance only when configured and needed:

```bash
export TRADINGAGENTS_NEWS_DATA_VENDOR=akshare_news,yfinance
```

Install the local data packages in the active Python environment:

```bash
pip install tushare akshare --upgrade
```

### 本地 Web 看板

本地 Web 由一个 Python HTTP 后端和静态前端组成，不需要另外安装 Node.js。后端读取 `reports/` 中由 CLI 保存的分析结果，前端负责展示总报告、各分析师分项、资金流量化信号、财务趋势、估值指标和抓取日志。

#### 启动前准备

先在仓库根目录运行一次分析并保存报告：

```bash
python -m cli.main
```

保存后，`reports/股票代码_时间/` 中应至少包含 `complete_report.md`；如果本次分析成功生成了量化策略，还会包含 `quant_strategy_report.md`。然后保持虚拟环境已激活，在同一目录启动本地服务：

```bash
python web/backend/server.py --host 127.0.0.1 --port 8765
```

浏览器打开 `http://127.0.0.1:8765`。服务默认只监听本机回环地址，不会自动暴露到公网；结束服务时在终端按 `Ctrl+C`。

#### Web 如何工作

页面打开后会执行以下流程：

1. 后端扫描 `reports/`，只列出包含 `complete_report.md` 的报告目录。
2. 前端默认加载最近更新的报告，也可以从左侧“历史报告”切换其他结果。
3. 后端解析 `quant_strategy_report.md`，提取量化信号、Day 0、参考买入价、止盈价、风险退出价和最近 15 个交易日的数据。
4. 页面按股票代码和报告日期请求 Tushare 财务快照，展示营收、利润、现金流、ROE、负债率、PE/PB 等信息。
5. 输入新的股票代码和分析日期并点击“生成实时量化策略”时，后端会重新调用 Tushare 日线与资金流接口计算结果；点击“刷新财务快照”会重新加载相应日期的基本面数据。

主要本地接口如下：

| 接口 | 作用 |
|---|---|
| `GET /api/reports` | 列出本地历史报告 |
| `GET /api/reports/{报告目录}` | 读取报告正文、分项和已保存的量化摘要 |
| `GET /api/quant/{股票代码}?date=YYYY-MM-DD` | 按股票和日期重新计算量化策略 |
| `GET /api/fundamentals/{股票代码}?date=YYYY-MM-DD` | 加载财务和估值快照 |
| `GET /api/health` | 检查本地后端是否正常运行 |

“生成实时量化策略”中的“实时”表示按当前选择重新请求最新可用的数据并计算，不代表盘中逐笔行情。当前策略使用 Tushare 日线收盘价和日度资金流，因此交易日尚未收盘时，应以收盘后的完整数据再次确认。

#### 如何观察参考买入价和卖出价

在左侧输入 A 股代码，例如 `600519.SH`、`000001.SZ`，选择分析日期后点击“生成实时量化策略”。结果主要显示在页面顶部的“量化信号”“Day 0”“止盈 / 风险线”三张卡片中，完整计算过程可在下方“量化策略”标签查看。

策略规则如下：

1. 计算目标交易日前 10 个交易日的平均成交额。
2. 如果某日资金净流入为正，且达到此前 10 日平均成交额的 5%，该日被记为 `Day 0`。
3. `Day 0 close` 是策略的参考买入价，不是系统自动成交的真实价格。
4. 参考止盈价 = `Day 0 close × 1.20`。
5. 风控退出价 = `Day 0 close × 0.85`。
6. 信号最多监控 30 个自然日，超过后需要重新评估。

例如，页面显示 `Day 0 close = 100.00` 时：

| 观察项 | 价格 | 含义 |
|---|---:|---|
| 参考买入价 | `100.00` | 触发资金流条件当日的收盘价 |
| 参考止盈价 | `120.00` | 最新收盘价达到或超过该价格时触发止盈信号 |
| 风控退出价 | `85.00` | 最新收盘价达到或跌破该价格时触发减仓或退出信号 |

量化信号含义：

| 信号 | 如何处理 |
|---|---|
| `DATA_UNAVAILABLE` | 无法取得有效数据；检查 `TUSHARE_TOKEN`、`tushare` 安装、接口权限和网络 |
| `NO_BUY_SIGNAL` | 回看区间内没有达到 5% 资金净流入条件，继续观察 |
| `ACTIVE_BUY_OR_HOLD` | 已出现 Day 0，仍在 30 日窗口内且未触发上下边界 |
| `SELL_TAKE_PROFIT` | 最新收盘价已达到参考止盈价 |
| `REDUCE_OR_EXIT` | 最新收盘价已跌到风控退出价 |
| `EXPIRED` | Day 0 已超过 30 个自然日，旧信号不再直接使用 |

页面中的“主报告建议”来自多智能体研究和风险管理结论，“量化信号”来自独立的资金流规则，两者可能不同。实际决策应同时查看“新闻政策”“基本面”“组合决策”和“抓取日志”，并核对最新公告和真实可成交价格。本项目不会连接券商或自动提交订单，所有价格均为研究与策略观察参考，不构成投资建议。

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

An interface will appear showing results as they load, letting you track the agent's progress as it runs.

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## TradingAgents Package

### Implementation Details

We built TradingAgents with LangGraph to ensure flexibility and modularity. The framework supports multiple LLM providers: OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen (Alibaba DashScope, international and China endpoints), GLM (Zhipu), MiniMax (global + China), OpenRouter, Ollama for local models, and Azure OpenAI for enterprise.

### Python Usage

To use TradingAgents inside your code, you can import the `tradingagents` module and initialize a `TradingAgentsGraph()` object. The `.propagate()` function will return a decision. You can run `main.py`, here's also a quick example:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# forward propagate
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

You can also adjust the default configuration to set your own choice of LLMs, debate rounds, etc.

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # openai, google, anthropic, xai, deepseek, qwen, qwen-cn, glm, glm-cn, minimax, minimax-cn, openrouter, ollama, azure
config["deep_think_llm"] = "gpt-5.5"     # Model for complex reasoning
config["quick_think_llm"] = "gpt-5.4-mini" # Model for quick tasks
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

See `tradingagents/default_config.py` for all configuration options.

## Persistence and Recovery

TradingAgents persists two kinds of state across runs.

### Decision log

The decision log is always on. Each completed run appends its decision to `~/.tradingagents/memory/trading_memory.md`. On the next run for the same ticker, TradingAgents fetches the realised return (raw and alpha vs SPY), generates a one-paragraph reflection, and injects the most recent same-ticker decisions plus recent cross-ticker lessons into the Portfolio Manager prompt, so each analysis carries forward what worked and what didn't.

Override the path with `TRADINGAGENTS_MEMORY_LOG_PATH`.

### Checkpoint resume

Checkpoint resume is opt-in via `--checkpoint`. When enabled, LangGraph saves state after each node so a crashed or interrupted run resumes from the last successful step instead of starting over. On a resume run you will see `Resuming from step N for <TICKER> on <date>` in the logs; on a new run you will see `Starting fresh`. Checkpoints are cleared automatically on successful completion.

Per-ticker SQLite databases live at `~/.tradingagents/cache/checkpoints/<TICKER>.db` (override the base with `TRADINGAGENTS_CACHE_DIR`). Use `--clear-checkpoints` to reset all of them before a run.

```bash
tradingagents analyze --checkpoint           # enable for this run
tradingagents analyze --clear-checkpoints    # reset before running
```

```python
config = DEFAULT_CONFIG.copy()
config["checkpoint_enabled"] = True
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
```

## Reproducibility

TradingAgents is LLM-driven, so two runs of the same ticker and date can differ. This is expected for a research tool built on language models, not a defect. The variation comes from a few distinct sources, and it helps to separate them.

Language model sampling is non-deterministic. Even at a fixed temperature, providers do not guarantee byte-identical output across calls, and reasoning models (the default GPT-5.x family, and any thinking-mode model) vary the most because their internal reasoning is itself sampled.

Live data moves. News and market-event sources return different content as time passes, so a run today sees different inputs than a run last week even for the same historical trade date. Pin the analysis date to hold the price and indicator window fixed, but live news sources still reflect "now".

To reduce variation you can lower the sampling temperature. Set `temperature` in your config (or `TRADINGAGENTS_TEMPERATURE` in `.env`); lower values make models that honor it more repeatable. Reasoning models largely ignore temperature, so for tighter reproducibility pair a low temperature with a non-reasoning model such as `gpt-4.1`.

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["deep_think_llm"] = "gpt-4.1"      # non-reasoning model honors temperature
config["quick_think_llm"] = "gpt-4.1"
config["temperature"] = 0.0
```

What does not vary anymore: the analyzed company identity is resolved deterministically from the ticker before any agent runs, and the market analyst grounds exact price and indicator claims in a verified data snapshot. Earlier reports of "different companies" or fabricated price levels across runs are addressed by these two mechanisms.

Backtest results are not guaranteed to match any published figure. Returns depend on the model, the temperature, the date range, data quality, and the sampling above. Treat the framework as a research scaffold for studying multi-agent analysis, not as a strategy with a fixed, replicable return.

## Contributing

Contributions are welcome: bug fixes, documentation, and feature ideas; past contributions are credited per release in [`CHANGELOG.md`](CHANGELOG.md).

## Citation

Please reference our work if you find *TradingAgents* provides you with some help :)

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```
