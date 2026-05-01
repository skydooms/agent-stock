# 智投研 — 基于 Hermes Agent 的多 Agent 股票情报与自动化分析工程

## 项目概览
本项目是基于 **Hermes Agent** 框架构建的端到端股票情报自动化系统，网关集成 **飞书（Lark）**。
核心能力覆盖：行业产业链系统性分析、新闻搜集与情绪影响评估、大盘/ETF/个股技术面分析（11种内置策略）、跟踪报告定时更新、Web 可视化看板、PTrade 本地回测及基于 Hermes RL 流水线的策略自优化。
目标：打造可定时运行、可人机协作、可自我进化的量化研究 Agent 集群。

## 技术栈
- **Agent 框架**: Hermes Agent (Nous Research) — Python SDK, v3.x
- **语言**: Python 3.11+
- **数据接口**: 
  - A股行情：AKShare / Tushare Pro
  - 财报/新闻：AKShare, 东方财富, 同花顺 iFinD (可选)
  - 指标计算：TA-Lib, pandas-ta, NumPy, Pandas
- **回测引擎**: SimTradeLab（PTrade API 本地仿真，零代码迁移）[^42^]
- **RL 训练**: Hermes 内置 Tinker-Atropos 流水线（GRPO + LoRA）[^33^]
- **Web 端**: 
  - 后端：FastAPI + Uvicorn
  - 前端：React 18 + TypeScript + Ant Design + ECharts
  - 数据库：SQLite（开发）/ PostgreSQL（生产）
  - 实时通信：WebSocket（推送热榜与告警）
- **网关**: 飞书自定义机器人（Webhook）+ 飞书事件订阅（可选）
- **定时任务**: Hermes 内置 Cron + APScheduler（本地兜底）
- **报告格式**: Markdown（含表格、Mermaid 流程图、ECharts 图片链接）

## "gstack" 
Use the /browse skill from gstack for all web browsing, never use mcp__claude-in-chrome__* tools.
A vailable skills: /office-hours, /plan-ceo-review, /plan-eng-review, /plan-design-review, /design-consultation, /design-shotgun, /design-html, /review, /ship, /land-and-deploy, /canary, /benchmark, /browse, /connect-chrome, /qa, /qa-only, /design-review, /setup-browser-cookies, /setup-deploy, /setup-gbrain, /retro, /investigate, /document-release, /codex, /cso, /autoplan, /plan-devex-review, /devex-review, /careful, /freeze, /guard, /unfreeze, /gstack-upgrade, /learn. 

## 核心功能与 Agent 映射

| 功能编号 | 功能描述 | 主责 Agent | 协作 Agent | 输出产物 |
|---|---|---|---|---|
| F1 | 行业系统性分析（上中下游股票罗列） | IndustryAnalyst | NewsCollector, ReportWriter | `industry_{{name}}_analysis.md` |
| F2 | 新闻搜集 + 板块/个股影响 + 情绪分析 | NewsCollector, NewsImpactAnalyzer | SentimentAnalyzer | `news_digest_{{date}}.json`, `impact_report.md` |
| F3 | 大盘指数技术面分析（11种策略） | MarketTechAnalyst | ReportWriter | `market_tech_{{index}}.md` |
| F4 | 行业指数/ETF 技术面分析（11种策略） | MarketTechAnalyst | ReportWriter | `etf_tech_{{code}}.md` |
| F5 | 个股技术面分析 + 系统性打分 | StockTechAnalyst | MarketTechAnalyst, NewsImpactAnalyzer | `stock_score_{{code}}.md` |
| F6 | 跟踪板块/个股，定时更新报告（1-2天） | TrackerUpdater | 所有分析 Agent | 增量更新 `.md` 报告 |
| F7 | Web 端看板（热榜、关注列表、标签管理） | WebDashboardAgent | Orchestrator | REST API + WebSocket |
| F8 | PTrade 回测 + RL 策略优化 | TradeTester, RLTrainer | Orchestrator | 回测统计 JSON + 优化后策略代码 |

## 多 Agent 协作架构（Mermaid）
