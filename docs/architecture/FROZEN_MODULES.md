# Frozen Modules Registry

> 版本：v0.1  
> 日期：2026-07-11  
> 状态：Active  
> 目的：记录进入冻结状态的模块，防止迁移期旧链路继续增长。

---

## 1. Frozen Modules

### 1.1 FormalReviewProjectionCompiler

模块：

```text
stock_processing_service/application/services/daily_review/formal_review_projection_compiler.py
stock_processing_service/application/services/daily_review/projections/*
```

状态：

```text
Frozen
```

允许：

1. bug fix。
2. test fix。
3. 现有兼容逻辑修复。
4. 不改变 schema 的小范围稳定性修复。

禁止：

1. schema expansion。
2. 新增业务字段。
3. 新增业务逻辑。
4. 新增 datasource。
5. 将 ReviewDocument section 回填到 FormalReviewProjectionCompiler。
6. 为了前端展示继续扩展 `formal_review`。

原因：

```text
Phase 4.5.7 起，ReviewDocument 是唯一增长的复盘展示协议。
FormalReviewProjectionCompiler 只作为 Phase 4.5.6 兼容层保留。
```

---

## 2. Review Requirement

任何 PR 若修改 frozen module，必须在 PR 描述中说明：

1. 是否为 bug fix。
2. 是否改变输出 schema。
3. 是否新增数据源。
4. 是否可以通过 ReviewDocument 替代。

不满足以上说明的 PR 不应合并。

