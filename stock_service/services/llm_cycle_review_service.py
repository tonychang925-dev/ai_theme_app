from __future__ import annotations

import json
import os
import aiohttp
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import asyncpg

from stock_service.config import StockServiceConfig


@dataclass
class CycleReviewInput:
    """LLM复核输入数据

    包含四层证据的完整信息，用于LLM复核
    """
    # 基础信息
    trade_date: str
    subject_key: str
    theme_name: str

    # 规则层输出
    cycle_state_rule: str
    mainline_alive_rule: bool
    fade_watch: bool
    fade_confirmed: bool

    # 评分字段
    mainline_strength_score: float
    fade_watch_score: float
    fade_confirmed_score: float
    divergence_score: float
    repair_score: float
    confidence_score: float

    # 四层证据详情
    event_layer: Dict[str, Any]
    leader_layer: Dict[str, Any]
    board_structure_layer: Dict[str, Any]
    theme_kline_layer: Dict[str, Any]

    # 状态转换信息
    previous_cycle_state: Optional[str]
    state_transition_reason: Optional[str]

    # 证据引用（用于追溯）
    evidence_refs: List[Dict[str, Any]]


@dataclass
class CycleReviewOutput:
    """LLM复核输出结构

    严格遵循设计文档15.4.3节格式
    """
    cycle_state_llm: str  # start|fermentation|acceleration|divergence|repair|fade_watch|fade_confirmed
    mainline_alive_llm: bool
    support_fade_confirmed: bool
    confidence: int  # 0-100
    reasons: List[str]
    risk_flags: List[str]

    # 复核意见详情
    agreement_with_rule: bool  # 是否同意规则层结论
    suggested_changes: List[str]  # 建议的变更
    evidence_quality_score: int  # 证据质量评分 0-100


class LlmCycleReviewService:
    """主线周期LLM复核服务

    实现固定Prompt模板和结构化输出
    严格遵循设计文档7.1-7.3节和15.4节要求
    """

    # 固定Prompt版本
    PROMPT_VERSION = "cycle_review_prompt.v1"

    # LLM模型配置（可扩展）
    MODEL_NAME = "deepseek-chat"  # 可根据实际配置调整
    API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")

    def __init__(self, config=None):
        self.config = config or StockServiceConfig()
        self._pool: Optional[asyncpg.Pool] = None

    @staticmethod
    def _load_env_file(env_file_path: str = ".env.theme") -> Dict[str, str]:
        """从 .env.theme 读取键值（仅用于补充运行时环境变量）。"""
        env_vars: Dict[str, str] = {}
        try:
            env_path = Path(env_file_path)
            if not env_path.exists():
                return env_vars
            with open(env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
        except Exception:
            return {}
        return env_vars

    def _get_deepseek_api_key(self) -> str:
        """优先读运行时环境变量；未设置时回退 .env.theme。"""
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if api_key:
            return api_key
        env_vars = self._load_env_file(".env.theme")
        return str(env_vars.get("DEEPSEEK_API_KEY", "")).strip()

    async def _ensure_pool(self) -> asyncpg.Pool:
        """确保数据库连接池存在"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                database=self.config.postgres_database,
                min_size=1,
                max_size=5
            )
        return self._pool

    async def close(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None

    def build_review_prompt(self, input_data: CycleReviewInput) -> str:
        """构建固定Prompt模板

        严格按照设计文档要求，确保输出结构化
        """
        # 格式化证据摘要
        evidence_summary = self._format_evidence_summary(input_data)

        # 规则层结论摘要
        rule_summary = self._format_rule_summary(input_data)

        prompt = f"""## 主线周期复核任务

### 置顶规则（最高优先级，必须严格执行）
以下规则来自《如何建立正确的交易体系.pdf》，优先级高于其他描述：

1. 主线定义必须同时满足两大维度，缺一不可：
   - 逻辑维度：题材具备“新颖度 + 时机 + 影响广度”中的有效支撑（可结合事件强度、连续性、时效性、题材技术支撑综合判断）
   - 市场维度：题材持续被资金认可（可结合龙头存活、接力强度、涨停/跌停结构、红盘比例综合判断）
2. 若任一维度证据不足，`mainline_alive_llm` 必须为 `false`，不得给出“主线存活”结论。
3. 禁止把“一日游题材/单日异动”判为主线；当持续性不足时，优先判 `fade_watch` 或 `divergence`。
4. 你的角色是“受控复核”，不是自由预测：只能基于输入证据做状态纠偏，不能创造新事实。

### 基础信息
- 交易日：{input_data.trade_date}
- 主题KEY：{input_data.subject_key}
- 主题名称：{input_data.theme_name}
- 前一日状态：{input_data.previous_cycle_state or "无历史记录"}

### 规则层结论
{rule_summary}

### 四层证据详情
{evidence_summary}

### 复核要求
请你作为主线周期复核专家，对上述规则层结论进行复核。你需要：

1. **复核周期状态**：从以下选项中选择最合适的周期状态：
   - start（启动）
   - fermentation（发酵）
   - acceleration（加速）
   - divergence（分歧）
   - repair（修复）
   - fade_watch（退潮观察）
   - fade_confirmed（退潮确认）

2. **复核主线存活**：判断主题是否仍有主线行情（true/false）

3. **支持退潮确认**：仅当证据充分时支持退潮确认（true/false）

4. **提供理由**：列出支持你结论的1-3条关键理由

5. **标注风险**：列出1-3个潜在风险点

### 输出格式（必须严格遵循JSON格式）
```json
{{
  "cycle_state_llm": "start|fermentation|acceleration|divergence|repair|fade_watch|fade_confirmed",
  "mainline_alive_llm": true,
  "support_fade_confirmed": false,
  "confidence": 85,
  "reasons": ["理由1", "理由2", "理由3"],
  "risk_flags": ["风险点1", "风险点2"]
}}
```

### 复核原则
1. 证据不足时禁止强行判fade_confirmed
2. 不得创造无事实支撑的新结论
3. 不得覆盖、篡改原始证据字段
4. fade_watch可复核为divergence（如果分歧特征更明显）
5. fade_watch可复核为fade_confirmed（仅当退潮证据充分）
6. `mainline_alive_llm=true` 必须满足“逻辑维度 + 市场维度”同时成立

请严格基于上述证据和规则层结论进行复核，输出JSON格式结果。
"""
        return prompt

    def _format_evidence_summary(self, input_data: CycleReviewInput) -> str:
        """格式化证据摘要"""
        summary = []

        # 事件层
        event = input_data.event_layer
        summary.append("**事件层证据**")
        summary.append(f"- 事件强度评分：{event.get('event_strength_score', 0):.1f}")
        summary.append(f"- 事件连续性评分：{event.get('event_continuity_score', 0):.1f}")
        summary.append(f"- 7日内强事件数量：{event.get('strong_event_count_7d', 0)}")
        recency = event.get('event_recency_days', '无事件')
        summary.append(f"- 最近事件天数：{recency}")

        # 龙头层
        leader = input_data.leader_layer
        summary.append("\n**龙头/接力层证据**")
        summary.append(f"- 龙头存活评分：{leader.get('leader_alive_score', 0):.1f}")
        summary.append(f"- 龙头破位标志：{leader.get('leader_breakdown_flag', False)}")
        summary.append(f"- 接力强度评分：{leader.get('relay_strength_score', 0):.1f}")
        summary.append(f"- 前排存活率：{leader.get('front_row_survival_ratio', 0):.2f}")

        # 板块结构层
        board = input_data.board_structure_layer
        summary.append("\n**板块结构层证据**")
        summary.append(f"- 涨停数量：{board.get('limit_up_count', 0)}")
        summary.append(f"- 跌停数量：{board.get('limit_down_count', 0)}")
        summary.append(f"- 红盘比例：{board.get('red_ratio', 0):.2f}")
        summary.append(f"- 大跌比例：{board.get('big_drop_ratio', 0):.2f}")
        summary.append(f"- 前排强度评分：{board.get('front_row_strength_score', 0):.1f}")

        # K线层
        kline = input_data.theme_kline_layer
        summary.append("\n**板块K线技术层证据**")
        summary.append(f"- 板块支撑评分：{kline.get('theme_support_score', 0):.1f}")
        summary.append(f"- 跌破启动枢轴：{kline.get('break_start_pivot', False)}")
        summary.append(f"- 3日收益：{kline.get('theme_ret_3d', 0):.2f}%")
        summary.append(f"- 5日收益：{kline.get('theme_ret_5d', 0):.2f}%")
        summary.append(f"- 10日收益：{kline.get('theme_ret_10d', 0):.2f}%")

        return "\n".join(summary)

    def _format_rule_summary(self, input_data: CycleReviewInput) -> str:
        """格式化规则层结论摘要"""
        summary = []

        summary.append(f"- **周期状态**：{input_data.cycle_state_rule}")
        summary.append(f"- **主线存活**：{input_data.mainline_alive_rule}")
        summary.append(f"- **退潮观察**：{input_data.fade_watch}")
        summary.append(f"- **退潮确认**：{input_data.fade_confirmed}")
        summary.append(f"- **主线强度评分**：{input_data.mainline_strength_score:.1f}")
        summary.append(f"- **退潮观察评分**：{input_data.fade_watch_score:.1f}")
        summary.append(f"- **退潮确认评分**：{input_data.fade_confirmed_score:.1f}")
        summary.append(f"- **分歧评分**：{input_data.divergence_score:.1f}")
        summary.append(f"- **修复评分**：{input_data.repair_score:.1f}")

        return "\n".join(summary)

    async def call_llm_for_review(self, prompt: str) -> Dict[str, Any]:
        """调用LLM进行复核

        实际调用DeepSeek API。
        无 API key / 调用异常时抛出异常，由上层走保守回退（维持规则层结论）。
        """
        api_key = self._get_deepseek_api_key()
        if not api_key:
            raise RuntimeError("missing_deepseek_api_key")

        # 实际调用DeepSeek API
        try:
            url = f"{self.API_BASE}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.MODEL_NAME,
                "messages": [
                    {"role": "system", "content": "你是一个主线周期复核专家，必须严格输出JSON格式。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 2000,
                "response_format": {"type": "json_object"}
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=30) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"❌ DeepSeek API调用失败: {response.status}, {error_text}")
                        raise Exception(f"API调用失败: {response.status}")

                    result = await response.json()
                    content = result["choices"][0]["message"]["content"]
                    # 解析JSON内容
                    llm_response = json.loads(content)
                    return llm_response

        except Exception as e:
            print(f"❌ LLM复核API调用异常: {e}")
            raise

    def parse_llm_response(self, raw_response: Dict[str, Any]) -> CycleReviewOutput:
        """解析LLM响应，确保输出结构化

        严格遵循设计文档15.4.3节格式
        """
        # 提取响应数据
        cycle_state_llm = str(raw_response.get("cycle_state_llm", "")).strip()
        mainline_alive_llm = bool(raw_response.get("mainline_alive_llm", False))
        support_fade_confirmed = bool(raw_response.get("support_fade_confirmed", False))
        confidence = int(raw_response.get("confidence", 0))

        # 验证周期状态合法性
        valid_states = {"start", "fermentation", "acceleration", "divergence",
                       "repair", "fade_watch", "fade_confirmed"}
        if cycle_state_llm not in valid_states:
            cycle_state_llm = "start"  # 默认值

        # 验证置信度范围
        confidence = max(0, min(100, confidence))

        # 解析理由列表
        reasons_raw = raw_response.get("reasons", [])
        if not isinstance(reasons_raw, list):
            reasons_raw = [reasons_raw] if reasons_raw else []
        reasons = [str(r).strip() for r in reasons_raw if str(r).strip()]

        # 解析风险标志
        risk_flags_raw = raw_response.get("risk_flags", [])
        if not isinstance(risk_flags_raw, list):
            risk_flags_raw = [risk_flags_raw] if risk_flags_raw else []
        risk_flags = [str(f).strip() for f in risk_flags_raw if str(f).strip()]

        # 计算与规则层的同意程度
        # 这里简化处理，实际可根据业务逻辑计算
        agreement_with_rule = True  # 默认同意

        # 建议的变更
        suggested_changes = []

        # 证据质量评分（简化）
        evidence_quality_score = 75

        return CycleReviewOutput(
            cycle_state_llm=cycle_state_llm,
            mainline_alive_llm=mainline_alive_llm,
            support_fade_confirmed=support_fade_confirmed,
            confidence=confidence,
            reasons=reasons,
            risk_flags=risk_flags,
            agreement_with_rule=agreement_with_rule,
            suggested_changes=suggested_changes,
            evidence_quality_score=evidence_quality_score
        )

    async def review_cycle_judgement(self, input_data: CycleReviewInput) -> CycleReviewOutput:
        """执行主线周期复核

        完整流程：构建Prompt -> 调用LLM -> 解析响应
        """
        try:
            # 1. 构建固定Prompt
            prompt = self.build_review_prompt(input_data)

            # 2. 调用LLM
            llm_response = await self.call_llm_for_review(prompt)

            # 3. 解析响应
            review_output = self.parse_llm_response(llm_response)

            return review_output

        except Exception as e:
            print(f"❌ LLM复核失败: {e}")
            # 返回默认复核结果（保守策略）
            return CycleReviewOutput(
                cycle_state_llm=input_data.cycle_state_rule,  # 维持规则层结论
                mainline_alive_llm=input_data.mainline_alive_rule,
                support_fade_confirmed=input_data.fade_confirmed,
                confidence=50,  # 低置信度
                reasons=[f"复核过程异常: {str(e)}"],
                risk_flags=["LLM复核服务异常"],
                agreement_with_rule=True,
                suggested_changes=[],
                evidence_quality_score=50
            )

    async def batch_review_for_date(self, trade_date: str) -> Dict[str, Any]:
        """批量复核指定交易日所有主题

        返回统计信息
        """
        pool = await self._ensure_pool()
        async with pool.acquire() as read_conn:
            # 获取需要复核的主题列表
            sql = """
            SELECT
                v2.*,
                e.event_strength_score, e.event_continuity_score,
                e.strong_event_count_7d, e.event_recency_days,
                e.leader_alive_score, e.leader_breakdown_flag,
                e.relay_strength_score, e.front_row_survival_ratio,
                e.limit_up_count, e.limit_down_count, e.red_ratio,
                e.big_drop_ratio, e.front_row_strength_score,
                e.theme_support_score, e.break_start_pivot,
                e.theme_ret_3d, e.theme_ret_5d, e.theme_ret_10d
            FROM theme_cycle_judgement_v2 v2
            LEFT JOIN theme_cycle_evidence_daily e
                ON v2.trade_date = e.trade_date
                AND v2.subject_key = e.subject_key
            WHERE v2.trade_date = $1
            """
            rows = await read_conn.fetch(sql, trade_date)

        results = []
        success_count = 0
        fail_count = 0

        for row in rows:
            try:
                # 构建复核输入
                input_data = self._build_review_input_from_row(row)

                # 执行复核
                review_output = await self.review_cycle_judgement(input_data)

                # 保存复核结果到数据库
                async with pool.acquire() as write_conn:
                    await self._save_review_result(write_conn, trade_date, row["subject_key"], review_output)

                results.append({
                    "subject_key": row["subject_key"],
                    "cycle_state_rule": row["cycle_state_rule"],
                    "cycle_state_llm": review_output.cycle_state_llm,
                    "agreement": review_output.agreement_with_rule
                })

                success_count += 1

            except Exception as e:
                print(f"❌ 主题 {row.get('subject_key', 'unknown')} 复核失败: {e}")
                fail_count += 1

        return {
            "trade_date": trade_date,
            "total": len(rows),
            "success": success_count,
            "failed": fail_count,
            "results": results
        }

    def _build_review_input_from_row(self, row) -> CycleReviewInput:
        """从数据库行构建复核输入"""
        return CycleReviewInput(
            trade_date=str(row["trade_date"]),
            subject_key=str(row["subject_key"]),
            theme_name=str(row.get("theme_name", "")),

            cycle_state_rule=str(row["cycle_state_rule"]),
            mainline_alive_rule=bool(row["mainline_alive_rule"]),
            fade_watch=bool(row["fade_watch"]),
            fade_confirmed=bool(row["fade_confirmed"]),

            mainline_strength_score=float(row.get("mainline_strength_score", 0)),
            fade_watch_score=float(row.get("fade_watch_score", 0)),
            fade_confirmed_score=float(row.get("fade_confirmed_score", 0)),
            divergence_score=float(row.get("divergence_score", 0)),
            repair_score=float(row.get("repair_score", 0)),
            confidence_score=float(row.get("confidence_score", 0)),

            event_layer={
                "event_strength_score": float(row.get("event_strength_score", 0)),
                "event_continuity_score": float(row.get("event_continuity_score", 0)),
                "strong_event_count_7d": int(row.get("strong_event_count_7d", 0)),
                "event_recency_days": row.get("event_recency_days")
            },
            leader_layer={
                "leader_alive_score": float(row.get("leader_alive_score", 0)),
                "leader_breakdown_flag": bool(row.get("leader_breakdown_flag", False)),
                "relay_strength_score": float(row.get("relay_strength_score", 0)),
                "front_row_survival_ratio": float(row.get("front_row_survival_ratio", 0))
            },
            board_structure_layer={
                "limit_up_count": int(row.get("limit_up_count", 0)),
                "limit_down_count": int(row.get("limit_down_count", 0)),
                "red_ratio": float(row.get("red_ratio", 0)),
                "big_drop_ratio": float(row.get("big_drop_ratio", 0)),
                "front_row_strength_score": float(row.get("front_row_strength_score", 0))
            },
            theme_kline_layer={
                "theme_support_score": float(row.get("theme_support_score", 0)),
                "break_start_pivot": bool(row.get("break_start_pivot", False)),
                "theme_ret_3d": float(row.get("theme_ret_3d", 0)),
                "theme_ret_5d": float(row.get("theme_ret_5d", 0)),
                "theme_ret_10d": float(row.get("theme_ret_10d", 0))
            },

            previous_cycle_state=row.get("previous_cycle_state"),
            state_transition_reason=row.get("state_transition_reason"),

            evidence_refs=[]
        )

    async def _save_review_result(self, conn: asyncpg.Connection,
                                 trade_date: str, subject_key: str,
                                 review_output: CycleReviewOutput) -> None:
        """保存复核结果到数据库"""
        sql = """
        UPDATE theme_cycle_judgement_v2
        SET
            cycle_state_llm = $3,
            mainline_alive_llm = $4,
            llm_reasons = $5,
            risk_flags = $6,
            confidence_score = $7,
            source_version = $8,
            llm_prompt_version = $9
        WHERE trade_date = $1 AND subject_key = $2
        """

        await conn.execute(
            sql,
            trade_date,
            subject_key,
            review_output.cycle_state_llm,
            review_output.mainline_alive_llm,
            json.dumps(review_output.reasons, ensure_ascii=False),
            json.dumps(review_output.risk_flags, ensure_ascii=False),
            review_output.confidence,
            "theme_cycle_judgement.v2_llm",
            self.PROMPT_VERSION
        )


async def main():
    """测试函数"""
    import sys
    from datetime import date

    if len(sys.argv) > 1:
        test_date = sys.argv[1]
    else:
        test_date = date(2026, 4, 7).isoformat()

    service = LlmCycleReviewService()
    try:
        print(f"🔍 开始LLM复核测试，日期: {test_date}")

        # 测试批量复核
        result = await service.batch_review_for_date(test_date)

        print(f"📊 LLM批量复核完成")
        print(f"   总计: {result['total']} 个主题")
        print(f"   成功: {result['success']}")
        print(f"   失败: {result['failed']}")

        # 打印前5个结果
        print(f"\n前5个复核结果:")
        for i, r in enumerate(result['results'][:5]):
            print(f"  {i+1}. {r['subject_key']}: rule={r['cycle_state_rule']}, llm={r['cycle_state_llm']}, agreement={r['agreement']}")

    finally:
        await service.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
