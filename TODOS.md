# TODOS

## plan-eng-review

### SQLite 缓存过期清理机制

**What:** 为 CacheManager 添加过期记录清理逻辑。

**Why:** 当前有 TTL 设置（K 线 1 天、新闻 4 小时）但没有实际清理机制，SQLite 文件会无限增长。

**Context:** CacheManager 使用 SQLite 存储 AKShare K 线数据和新闻结果。每次 `set()` 写入时应顺带调用 `prune_expired()` 删除超过 TTL 的记录，或定期批量清理。需在实现 CacheManager 时一并完成。

**Effort:** S
**Priority:** P1
**Depends on:** CacheManager 实现

### 评分阈值回测验证

**What:** 用历史 A 股数据回测综合评分阈值（≥80 买入 / 50-79 持有 / <50 卖出）的有效性。

**Why:** 当前阈值是经验硬编码，未经验证。回测能确认这些阈值在实际历史中是否具有区分度。

**Context:** 需要收集至少 6-12 个月的历史数据，计算每日综合评分，对比次日/次周收益率，统计各阈值区间的胜率和盈亏比。可在 F8（回测引擎）里程碑中实施，或先用 pandas 做简单回测。

**Effort:** M
**Priority:** P2
**Depends on:** F2+F5 稳定运行，历史数据可用

### 日志轮转配置

**What:** 配置 `RotatingFileHandler` 或 `TimedRotatingFileHandler`，限制日志文件大小和保留数量。

**Why:** 长期运行后日志文件会无限增长，可能占满磁盘。

**Context:** 当前计划使用标准库 `logging` 输出结构化日志。应在 `logging.basicConfig` 或 `logging.handlers` 中配置轮转策略（如单个文件 10MB，保留 5 个备份）。可在项目骨架阶段一并配置。

**Effort:** S
**Priority:** P2
**Depends on:** 日志模块实现

## Completed
