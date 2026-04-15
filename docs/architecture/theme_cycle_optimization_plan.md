# 主线周期判定优化方案（基于现有代码）

## 1. 背景与目标

### 1.1 问题识别
基于对现有代码的分析，发现以下核心问题：

1. **硬门槛过滤导致误杀**：`WeakToStrongCandidateBuilder`中`strong_background`和`repair_window`硬门槛过滤掉大量潜在候选
2. **主线判定过于简单**：现有`MainlineJudgementService`仅基于事件链+市场承认，缺乏多维度证据
3. **缺乏状态追踪**：`CycleJudgementService`无历史状态追踪，无法识别状态转换
4. **退潮状态未细分**：只有`is_fade`布尔值，无`fade_watch`/`fade_confirmed`区分
5. **候选池准入单一**：只有正式候选，无观察流机制

### 1.2 优化目标
- **保持向后兼容**：不推翻现有架构，在现有代码基础上渐进式优化
- **解决硬门槛问题**：将布尔过滤改为连续评分，降低误杀率
- **增强主线判定**：集成四层证据体系，提高判定准确性
- **完善状态追踪**：添加状态机，支持`previous_cycle_state`追踪
- **扩展候选池**：增加`observe_only`观察流，提高信号覆盖

## 2. 现有代码架构分析

### 2.1 核心服务模块

#### 2.1.1 MainlineJudgementService
- **位置**：`stock_service/services/mainline_judgement_service.py`
- **功能**：基于"事件链 + 市场承认"生成主线题材判断
- **输出**：`ThemeMainlineJudgement`（包含`is_main_theme`布尔值）
- **问题**：判定逻辑简单，仅使用事件计数和涨停数

#### 2.1.2 CycleJudgementService
- **位置**：`stock_service/services/cycle_judgement_service.py`
- **功能**：基于"主线 + 周期位置 + 动作建议"生成题材周期判断
- **输出**：`ThemeCycleJudgement`（包含`is_fade`等布尔字段）
- **问题**：无历史状态追踪，退潮状态未细分

#### 2.1.3 WeakToStrongCandidateBuilder
- **位置**：`stock_service/services/weak_to_strong_candidate_builder.py`
- **功能**：盘后弱转强候选池构建
- **问题**：硬门槛过滤过严（第169-187行）：
  ```python
  # 硬门槛1：强势背景
  strong_background = (
      is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3
  )
  if not strong_background:
      return None
  
  # 硬门槛2：分歧修复窗口
  repair_window = (
      ("弱转强" in action_bias)
      or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"}
      or is_divergence
      or is_rebound
      or is_fermentation
  )
  if is_fade:
      repair_window = False
  if not repair_window:
      return None
  ```

### 2.2 数据流程
```
主题事件数据 → MainlineJudgementService → theme_mainline_judgement表
                                       ↓
主题市场数据 → CycleJudgementService → theme_cycle_judgement表
                                       ↓
主题股票快照 → WeakToStrongCandidateBuilder → weak_to_strong_candidate_pool表
```

## 3. 优化方案设计

### 3.1 数据库扩展（已完成）
已创建迁移文件：`add_theme_cycle_v2_tables.sql`
- 新增`theme_cycle_evidence_daily`表：存放四层证据原始数据
- 新增`theme_cycle_judgement_v2`表：支持状态机追踪
- 扩展`weak_to_strong_candidate_pool`字段：增加`pool_entry_type`等

### 3.2 硬门槛优化方案

#### 3.2.1 将布尔过滤改为连续评分
**现有代码问题**：第169-187行硬门槛直接过滤
**优化方案**：改为评分机制，保留低分候选但标记为`observe_only`

```python
# 优化后：计算强势背景评分（0-100）
def _calculate_strong_background_score(self, is_leader, limit_up, recent_limit_up_count, rank_order):
    score = 0.0
    if is_leader:
        score += 40.0
    if limit_up:
        score += 30.0
    score += min(recent_limit_up_count * 15.0, 30.0)
    if rank_order <= 3:
        score += 20.0
    return min(score, 100.0)

# 优化后：计算修复窗口评分（0-100）
def _calculate_repair_window_score(self, action_bias, stage, is_divergence, is_rebound, is_fermentation, is_fade):
    score = 0.0
    if "弱转强" in action_bias:
        score += 40.0
    if stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"}:
        score += 30.0
    if is_divergence:
        score += 20.0
    if is_rebound:
        score += 15.0
    if is_fermentation:
        score += 10.0
    if is_fade:
        score -= 50.0  # 退潮主题大幅扣分，但不直接过滤
    return max(0.0, min(score, 100.0))
```

#### 3.2.2 候选池准入逻辑优化
**现有代码**：只有通过硬门槛才能进入候选池
**优化方案**：三级准入机制：
- **formal_allow**：强势背景≥60且修复窗口≥50且非退潮确认
- **observe_only**：强势背景≥30或修复窗口≥40，但未达正式标准
- **reject**：评分低于阈值

### 3.3 主线判定增强方案

#### 3.3.1 集成四层证据体系
在现有`MainlineJudgementService`基础上扩展，不替换原有逻辑：

```python
class EnhancedMainlineJudgementService(MainlineJudgementService):
    """增强版主线判定服务，集成四层证据"""
    
    def compute_evidence_layers(self, theme_data):
        """计算四层证据评分"""
        evidence_layers = {
            "event_driven": self._compute_event_layer(theme_data),
            "leader_relay": self._compute_leader_layer(theme_data),
            "board_structure": self._compute_board_layer(theme_data),
            "theme_kline": self._compute_kline_layer(theme_data)
        }
        return evidence_layers
    
    def compute_mainline_alive_score(self, evidence_layers, is_main_theme):
        """计算主线存活评分，替代硬布尔值"""
        # 综合四层证据计算主线强度
        strength_score = self._aggregate_evidence_scores(evidence_layers)
        
        # 主线存活条件公式（参考设计方案）
        mainline_alive = (
            is_main_theme 
            and strength_score >= 60 
            and evidence_layers["leader_relay"]["leader_alive_score"] >= 40
            and evidence_layers["event_driven"]["event_count_3d"] >= 1
        )
        return mainline_alive, strength_score
```

#### 3.3.2 保持向后兼容
- 保留原有`is_main_theme`字段，同时新增`mainline_strength_score`
- 原有调用代码无需修改，新增功能通过扩展方法提供

### 3.4 周期判定状态机方案

#### 3.4.1 状态追踪实现
扩展`CycleJudgementService`，添加状态转换逻辑：

```python
class EnhancedCycleJudgementService(CycleJudgementService):
    """增强版周期判定服务，支持状态机"""
    
    def __init__(self):
        super().__init__()
        self.state_machine = ThemeCycleStateMachine()
    
    def classify_cycle_with_history(self, current_inputs, previous_state):
        """考虑历史状态进行周期判定"""
        # 1. 基于当日数据计算初步阶段
        raw_stage = super().classify_primary_stage(*current_inputs)
        
        # 2. 应用状态转换规则
        final_stage = self.state_machine.transition(previous_state, raw_stage, current_inputs)
        
        # 3. 判断退潮状态细分
        fade_status = self._determine_fade_status(final_stage, current_inputs, previous_state)
        
        return final_stage, fade_status
    
    def _determine_fade_status(self, current_stage, inputs, previous_state):
        """判断退潮状态：fade_watch或fade_confirmed"""
        if current_stage == "fade":
            if previous_state in ["divergence", "rebound"]:
                return "fade_watch"  # 退潮观察
            elif previous_state in ["fade_watch", "fade"]:
                return "fade_confirmed"  # 退潮确认
            else:
                return "fade_watch"
        return "none"
```

#### 3.4.2 状态转换规则
参考设计方案中的状态机：
- `start` → `fermentation` → `acceleration` → `divergence` → `repair/fade_watch` → `fade_confirmed`
- 支持`repair`状态回归`fermentation`的修复路径

### 3.5 候选池准入优化方案

#### 3.5.1 三级准入标准
```python
class EnhancedCandidateBuilder(WeakToStrongCandidateBuilder):
    """增强版候选构建器，支持三级准入"""
    
    def determine_pool_entry_type(self, candidate_data):
        """确定候选池进入类型"""
        strong_bg_score = self._calculate_strong_background_score(*candidate_data)
        repair_score = self._calculate_repair_window_score(*candidate_data)
        mainline_alive = candidate_data.get("mainline_alive", False)
        fade_confirmed = candidate_data.get("fade_confirmed", False)
        
        # 正式准入条件
        if (strong_bg_score >= 60 and repair_score >= 50 and 
            mainline_alive and not fade_confirmed):
            return "formal"
        
        # 观察流条件
        elif (strong_bg_score >= 30 or repair_score >= 40) and not fade_confirmed:
            return "observe_only"
        
        # 拒绝
        else:
            return "reject"
    
    async def build_enhanced(self, trade_date, max_candidates=120):
        """增强版构建流程，保留观察流"""
        # 获取基础候选
        base_result = await super().build(trade_date, max_candidates=max_candidates*2)
        
        # 计算增强特征
        enhanced_candidates = []
        for candidate in base_result.candidates:
            # 计算主线周期特征
            cycle_features = await self._fetch_cycle_features(candidate)
            
            # 确定准入类型
            entry_type = self.determine_pool_entry_type({
                **candidate,
                **cycle_features
            })
            
            # 仅保留正式和观察流
            if entry_type != "reject":
                enhanced = {
                    **candidate,
                    "pool_entry_type": entry_type,
                    "cycle_state": cycle_features.get("cycle_state"),
                    "mainline_strength_score": cycle_features.get("mainline_strength_score"),
                    "fade_watch": cycle_features.get("fade_watch", False),
                    "fade_confirmed": cycle_features.get("fade_confirmed", False)
                }
                enhanced_candidates.append(enhanced)
        
        # 排序和截断
        enhanced_candidates.sort(key=lambda x: (
            0 if x["pool_entry_type"] == "formal" else 1,
            -float(x.get("candidate_score", 0))
        ))
        return enhanced_candidates[:max_candidates]
```

## 4. 实施计划

### 4.1 第一阶段：数据库扩展（1天）
- [x] 已创建迁移文件：`add_theme_cycle_v2_tables.sql`
- [ ] 执行数据库迁移
- [ ] 验证表结构和索引

### 4.2 第二阶段：核心服务增强（2天）
- [ ] 创建`EnhancedMainlineJudgementService`，集成四层证据
- [ ] 创建`EnhancedCycleJudgementService`，添加状态机
- [ ] 保持原有接口兼容性

### 4.3 第三阶段：候选构建器优化（2天）
- [ ] 创建`EnhancedCandidateBuilder`，替换硬门槛为评分
- [ ] 实现三级准入逻辑
- [ ] 集成主线周期特征查询

### 4.4 第四阶段：数据流水线整合（1天）
- [ ] 更新构建脚本，支持V2表写入
- [ ] 创建回填脚本，补充历史数据
- [ ] 验证端到端流程

### 4.5 第五阶段：测试与验证（2天）
- [ ] 单元测试：验证状态转换逻辑
- [ ] 集成测试：验证端到端流程
- [ ] 回测验证：对比优化前后候选质量

## 5. 风险控制

### 5.1 兼容性风险
- **应对**：保留原有接口，新增功能通过扩展类提供
- **回滚方案**：可随时切回原有服务

### 5.2 性能风险
- **应对**：新增表添加适当索引，分批处理历史数据
- **监控**：增加查询耗时监控

### 5.3 数据质量风险
- **应对**：分阶段上线，先观察流后正式流
- **验证**：对比优化前后候选数量和质量

## 6. 预期收益

### 6.1 质量提升
- **降低误杀率**：硬门槛改为评分，保留潜在优质候选
- **提高命中率**：多维度证据提升主线判定准确性
- **增强鲁棒性**：状态机追踪减少状态跳变

### 6.2 覆盖扩展
- **观察流机制**：覆盖更多边缘案例，提供早期信号
- **退潮状态细分**：更好识别退潮过程，避免过早过滤

### 6.3 可维护性
- **架构清晰**：证据层、判定层、状态层分离
- **扩展性强**：支持后续增加更多证据维度
- **监控完善**：新增字段支持更细粒度分析

## 7. 附录

### 7.1 关键代码位置
- 现有主线判定：`stock_service/services/mainline_judgement_service.py`
- 现有周期判定：`stock_service/services/cycle_judgement_service.py`
- 现有候选构建：`stock_service/services/weak_to_strong_candidate_builder.py`
- V2迁移文件：`stock_service/database/migrations/add_theme_cycle_v2_tables.sql`
- V2证据schema：`docs/architecture/theme_cycle_evidence_schema_v1.json`

### 7.2 依赖关系
- 需要先执行数据库迁移
- 需要补充主题事件数据源
- 需要主题K线数据支持

### 7.3 验收标准
1. 硬门槛过滤减少50%以上误杀
2. 观察流覆盖20-30%额外候选
3. 状态转换准确率≥90%
4. 整体性能影响≤10%
