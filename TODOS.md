# TODOS

## plan-eng-review

### 行业新闻整合到 IndustryAnalyst

**What:** F1 当前只产出基于行情快照的行业景气度，未整合行业级新闻。可让 IndustryAnalyst 调用 NewsCollector 拉取行业关键词新闻，并通过 NewsImpactAnalyzer 给出行业舆情影响分。

**Why:** CLAUDE.md 中 F1 表明协作 Agent 包含 NewsCollector，当前缺失。行业景气度仅依赖涨跌幅波动较大且受当日行情噪音影响。

**Context:** 在 `IndustryAnalyst.analyze` 中可选注入 `news_collector` 与 `news_impact`。行业关键词从 yaml 增加 `keywords:` 列表（如光伏 → "光伏 硅料 组件"）。综合景气度 = 行情景气度 * 0.6 + 舆情景气度 * 0.4。

**Effort:** M
**Priority:** P2
**Depends on:** F1 已完成

### 评分阈值回测验证

**What:** 用历史 A 股数据回测综合评分阈值（≥80 买入 / 50-79 持有 / <50 卖出）的有效性。

**Why:** 当前阈值是经验硬编码，未经验证。回测能确认这些阈值在实际历史中是否具有区分度。

**Context:** 需要收集至少 6-12 个月的历史数据，计算每日综合评分，对比次日/次周收益率，统计各阈值区间的胜率和盈亏比。可在 F8（回测引擎）里程碑中实施，或先用 pandas 做简单回测。

**Effort:** M
**Priority:** P2
**Depends on:** F2+F5 稳定运行，历史数据可用，F8 回测引擎搭建

## Completed

### F3 大盘指数技术面分析 + F4 ETF 技术面分析

**What:** MarketTechAnalyst Agent 输出 11 项技术指标加权综合评分, 复用 IndicatorEngine 扩展. 数据源 AKShare (`index_zh_a_hist` / `fund_etf_hist_em`).

**Resolved:** 已交付。
- **指标扩展**: IndicatorEngine 新增 7 项 (MA Cross / Volume / ATR / ADX / OBV / Williams %R / CCI), 加上原有 4 项 (MACD/KDJ/RSI/Bollinger) 共 11 项, 通过 `strategies=` 参数化保持 F5 个股向后兼容 (默认仍是 4 项)
- **数据获取**: DataFetcher 新增 `fetch_index(code)` 与 `fetch_etf(code)`, 各自独立 cache key 避免冲突
- **Agent**: `MarketTechAnalyst` 阈值 buy=75/hold=50, 单一 instance 通过 `render(payload, kind="index"|"etf")` 切换标题
- **模板**: `templates/market_tech_report.md.j2` 表格化展示 11 指标 + 综合评分 + 策略说明
- **CLI**: `agent-stock market 000001` 与 `agent-stock etf 510300` 子命令
- **Lark**: "大盘 / 大盘 上证 / 指数 399006 / ETF 510300 / etf 159915" 命令解析, 含 11 个常见指数中文别名
- **Web**: web_server `market` / `etf` action 处理
- **Orchestrator**: `run_market(code)` / `run_etf(code)`, 报告分别保存 `market_tech_*.md` / `etf_tech_*.md`
- **测试**: 14 个单测全过 (4 默认策略 + 11 全策略 + 渲染 + 数据不足 + Lark 命令解析 + 别名映射)

### F1 行业产业链系统性分析

**What:** 实现 IndustryAnalyst Agent，支持基于 `config/industry_chains.yaml` 的行业上中下游分级，自动拉取 AKShare 全市场快照计算节点平均涨跌与行业景气度，渲染 Markdown 报告。

**Resolved:** 已交付。包含模型 `IndustryStock/IndustryNode/IndustryAnalysis`、Jinja 模板 `templates/industry_report.md.j2`、CLI 子命令 `stock/industry`（向后兼容老用法）、Lark 事件订阅 `行业/板块/产业链` 命令解析、Web 端 `industry` action 处理、6 个单元测试全过。AKShare 失败时降级为 0 涨跌占位，不阻塞流程。预设 5 个行业（光伏 / 新能源汽车 / 半导体 / 锂电池 / 消费电子）。

### CLI 中文输出乱码

**What:** Windows cp936 控制台 print 中文出现 ����。

**Resolved:** `logging_config.force_utf8_stdio()` 工具方法，所有入口（cli / web_server / start_lark_tunnel）调用一次将 stdout/stderr 重新配置为 UTF-8。

### SQLite 缓存过期清理机制

**What:** 为 CacheManager 添加过期记录清理逻辑。

**Resolved:** 已在 `src/agent_stock/modules/cache.py` 实现。`set()` 写入时调用 `_prune_expired()` 删除 `created_at + ttl < now` 的记录；`get()` 命中过期记录时也会立即删除单条。

### 日志轮转配置

**What:** 配置 `RotatingFileHandler`，限制日志文件大小和保留数量。

**Resolved:** 已在 `src/agent_stock/logging_config.py` 实现。单文件 10MB，保留 5 份备份，UTF-8 编码，输出至 `.logs/agent_stock.log`。
