"""
选股器数据仓库 (asyncpg 版本)
"""

import json
import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import asyncpg

from stock_service.config import StockServiceConfig
from stock_service.stock_screener_models import (
    DEFAULT_STRATEGIES,
    DimensionScores,
    ScreeningExecution,
    ScreeningResult,
    ScreeningStrategy,
    UserFavorite,
)

logger = logging.getLogger(__name__)


class StockScreenerRepository:
    """选股器数据仓库"""

    def __init__(self, config: StockServiceConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize(self) -> None:
        """初始化数据库连接池"""
        if self.pool is not None:
            return

        self.pool = await asyncpg.create_pool(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            database=self.config.postgres_database,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
            min_size=1,
            max_size=5,
        )
        await self.ensure_schema()
        await self.initialize_default_strategies()

    async def ensure_schema(self) -> None:
        """确保选股器基础表存在（兼容未执行 migration 的环境）"""
        pool = await self._ensure_pool()
        ddl_statements = [
            """
            CREATE TABLE IF NOT EXISTS stock_screening_strategy (
                strategy_id VARCHAR(50) PRIMARY KEY,
                strategy_name VARCHAR(100) NOT NULL,
                strategy_type VARCHAR(20) NOT NULL,
                description TEXT,
                weight_config JSONB NOT NULL,
                filter_config JSONB NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(50)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS stock_screening_execution (
                execution_id VARCHAR(50) PRIMARY KEY,
                strategy_id VARCHAR(50) NOT NULL REFERENCES stock_screening_strategy(strategy_id),
                trade_date DATE NOT NULL,
                status VARCHAR(20) NOT NULL,
                total_stocks INTEGER DEFAULT 0,
                screened_stocks INTEGER DEFAULT 0,
                results_count INTEGER DEFAULT 0,
                execution_time_ms INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS stock_screening_result (
                result_id VARCHAR(50) PRIMARY KEY,
                strategy_id VARCHAR(50) NOT NULL REFERENCES stock_screening_strategy(strategy_id),
                execution_id VARCHAR(50) NOT NULL REFERENCES stock_screening_execution(execution_id),
                trade_date DATE NOT NULL,
                stock_id VARCHAR(20) NOT NULL,
                stock_name VARCHAR(100) NOT NULL,
                composite_score DECIMAL(5,2) NOT NULL,
                dimension_scores JSONB NOT NULL,
                rank_position INTEGER,
                screening_reason TEXT,
                theme_info JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_stock_screening_favorite (
                favorite_id VARCHAR(50) PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                result_id VARCHAR(50) NOT NULL REFERENCES stock_screening_result(result_id),
                notes TEXT,
                tags JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, result_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS stock_screening_llm_review (
                review_id VARCHAR(64) PRIMARY KEY,
                execution_id VARCHAR(50) NOT NULL REFERENCES stock_screening_execution(execution_id),
                strategy_id VARCHAR(50) NOT NULL REFERENCES stock_screening_strategy(strategy_id),
                result_id VARCHAR(50) NOT NULL REFERENCES stock_screening_result(result_id),
                stock_id VARCHAR(20) NOT NULL,
                trade_date DATE NOT NULL,
                decision VARCHAR(16) NOT NULL,
                llm_score DECIMAL(5,2),
                confidence DECIMAL(6,4),
                reasoning TEXT,
                risk_flags JSONB DEFAULT '[]'::jsonb,
                evidence_refs JSONB DEFAULT '[]'::jsonb,
                model_name VARCHAR(128),
                prompt_version VARCHAR(64),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(result_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_stock_screening_strategy_active ON stock_screening_strategy(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_stock_screening_execution_strategy_date ON stock_screening_execution(strategy_id, trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_stock_screening_execution_status ON stock_screening_execution(status)",
            "CREATE INDEX IF NOT EXISTS idx_stock_screening_result_execution ON stock_screening_result(execution_id)",
            "CREATE INDEX IF NOT EXISTS idx_stock_screening_result_trade_date ON stock_screening_result(trade_date)",
            "CREATE INDEX IF NOT EXISTS idx_stock_screening_result_stock ON stock_screening_result(stock_id)",
            "CREATE INDEX IF NOT EXISTS idx_stock_screening_result_score ON stock_screening_result(composite_score DESC)",
            "CREATE INDEX IF NOT EXISTS idx_user_favorite_user ON user_stock_screening_favorite(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_favorite_created ON user_stock_screening_favorite(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_stock_screening_llm_review_exec ON stock_screening_llm_review(execution_id)",
            "CREATE INDEX IF NOT EXISTS idx_stock_screening_llm_review_decision ON stock_screening_llm_review(decision)",
        ]
        try:
            async with pool.acquire() as conn:
                for ddl in ddl_statements:
                    await conn.execute(ddl)
                # 兼容旧结构：补齐运行时代码依赖列
                await conn.execute(
                    "ALTER TABLE stock_screening_execution "
                    "ADD COLUMN IF NOT EXISTS screened_stocks INTEGER DEFAULT 0"
                )
                await conn.execute(
                    "ALTER TABLE stock_screening_execution "
                    "ADD COLUMN IF NOT EXISTS results_count INTEGER DEFAULT 0"
                )
                await conn.execute(
                    "ALTER TABLE stock_screening_execution "
                    "ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                )
                # 若历史列 selected_stocks 存在，则迁移到 screened_stocks
                await conn.execute(
                    """
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'stock_screening_execution'
                              AND column_name = 'selected_stocks'
                        ) THEN
                            EXECUTE '
                                UPDATE stock_screening_execution
                                   SET screened_stocks = COALESCE(screened_stocks, selected_stocks, 0)
                                 WHERE screened_stocks IS NULL OR screened_stocks = 0
                            ';
                        END IF;
                    END $$;
                    """
                )
        except Exception as e:
            logger.error(f"确保选股器表结构失败: {e}")

    async def close(self) -> None:
        """关闭数据库连接池"""
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            await self.initialize()
        assert self.pool is not None
        return self.pool

    @staticmethod
    def _parse_json(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return default
        return default

    @staticmethod
    def _to_dimension_scores(value: Any) -> DimensionScores:
        payload = StockScreenerRepository._parse_json(value, {})
        return DimensionScores(
            mainline=float(payload.get("mainline", 0)),
            cycle=float(payload.get("cycle", 0)),
            leader=float(payload.get("leader", 0)),
            technical=float(payload.get("technical", 0)),
        )

    @staticmethod
    def _gen_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    async def initialize_default_strategies(self) -> None:
        """初始化默认策略"""
        pool = await self._ensure_pool()
        try:
            logger.info("检查并补齐默认选股策略")
            sql_insert = """
            INSERT INTO stock_screening_strategy (
                strategy_id,
                strategy_name,
                strategy_type,
                description,
                weight_config,
                filter_config,
                created_by,
                is_active,
                created_at,
                updated_at
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10)
            ON CONFLICT (strategy_id) DO NOTHING
            """

            async with pool.acquire() as conn:
                for strategy in DEFAULT_STRATEGIES:
                    await conn.execute(
                        sql_insert,
                        strategy.strategy_id,
                        strategy.strategy_name,
                        strategy.strategy_type,
                        strategy.description,
                        json.dumps(strategy.weight_config, ensure_ascii=False),
                        json.dumps(strategy.filter_config, ensure_ascii=False),
                        strategy.created_by,
                        strategy.is_active,
                        strategy.created_at,
                        strategy.updated_at,
                    )
        except Exception as e:
            logger.error(f"初始化默认策略失败: {e}")

    async def get_strategy(self, strategy_id: str) -> Optional[ScreeningStrategy]:
        """获取选股策略"""
        pool = await self._ensure_pool()
        sql = """
        SELECT strategy_id, strategy_name, strategy_type, description,
               weight_config, filter_config, created_at, updated_at,
               created_by, is_active
        FROM stock_screening_strategy
        WHERE strategy_id = $1
        """
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(sql, strategy_id)
            if not row:
                return None

            return ScreeningStrategy(
                strategy_id=row["strategy_id"],
                strategy_name=row["strategy_name"],
                strategy_type=row["strategy_type"],
                description=row["description"] or "",
                weight_config=self._parse_json(row["weight_config"], {}),
                filter_config=self._parse_json(row["filter_config"], {}),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                created_by=row["created_by"],
                is_active=bool(row["is_active"]),
            )
        except Exception as e:
            logger.error(f"获取策略失败 {strategy_id}: {e}")
            return None

    async def get_strategies(self, active_only: bool = True) -> List[ScreeningStrategy]:
        """获取选股策略列表"""
        pool = await self._ensure_pool()
        sql = """
        SELECT strategy_id, strategy_name, strategy_type, description,
               weight_config, filter_config, created_at, updated_at,
               created_by, is_active
        FROM stock_screening_strategy
        WHERE ($1::boolean = false OR is_active = true)
        ORDER BY created_at DESC
        """
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, active_only)

            return [
                ScreeningStrategy(
                    strategy_id=row["strategy_id"],
                    strategy_name=row["strategy_name"],
                    strategy_type=row["strategy_type"],
                    description=row["description"] or "",
                    weight_config=self._parse_json(row["weight_config"], {}),
                    filter_config=self._parse_json(row["filter_config"], {}),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    created_by=row["created_by"],
                    is_active=bool(row["is_active"]),
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(f"获取策略列表失败: {e}")
            return []

    async def create_strategy(self, strategy: ScreeningStrategy) -> Optional[ScreeningStrategy]:
        """创建选股策略"""
        pool = await self._ensure_pool()
        sql = """
        INSERT INTO stock_screening_strategy (
            strategy_id, strategy_name, strategy_type, description,
            weight_config, filter_config, created_at, updated_at,
            created_by, is_active
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10)
        """
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    sql,
                    strategy.strategy_id,
                    strategy.strategy_name,
                    strategy.strategy_type,
                    strategy.description,
                    json.dumps(strategy.weight_config, ensure_ascii=False),
                    json.dumps(strategy.filter_config, ensure_ascii=False),
                    strategy.created_at,
                    strategy.updated_at,
                    strategy.created_by,
                    strategy.is_active,
                )
            return strategy
        except Exception as e:
            logger.error(f"创建策略失败: {e}")
            return None

    async def update_strategy(self, strategy_id: str, updates: Dict[str, Any]) -> bool:
        """更新选股策略"""
        if not updates:
            return False

        pool = await self._ensure_pool()
        fields: List[str] = []
        values: List[Any] = []

        def add(field: str, value: Any) -> None:
            fields.append(f"{field} = ${len(values) + 1}")
            values.append(value)

        if "weight_config" in updates:
            add("weight_config", json.dumps(updates["weight_config"], ensure_ascii=False))
        if "filter_config" in updates:
            add("filter_config", json.dumps(updates["filter_config"], ensure_ascii=False))
        if "strategy_name" in updates:
            add("strategy_name", updates["strategy_name"])
        if "strategy_type" in updates:
            add("strategy_type", updates["strategy_type"])
        if "description" in updates:
            add("description", updates["description"])
        if "is_active" in updates:
            add("is_active", updates["is_active"])

        add("updated_at", datetime.now())
        values.append(strategy_id)

        sql = f"""
        UPDATE stock_screening_strategy
        SET {", ".join(fields)}
        WHERE strategy_id = ${len(values)}
        """

        try:
            async with pool.acquire() as conn:
                result = await conn.execute(sql, *values)
            return result.upper().startswith("UPDATE 1")
        except Exception as e:
            logger.error(f"更新策略失败 {strategy_id}: {e}")
            return False

    async def save_results(self, results: List[ScreeningResult], execution_id: str) -> bool:
        """保存选股结果"""
        if not results:
            return True

        pool = await self._ensure_pool()
        sql = """
        INSERT INTO stock_screening_result (
            result_id,
            strategy_id,
            execution_id,
            trade_date,
            stock_id,
            stock_name,
            composite_score,
            dimension_scores,
            rank_position,
            screening_reason,
            theme_info,
            created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11::jsonb, $12
        )
        ON CONFLICT (result_id) DO UPDATE SET
            composite_score = EXCLUDED.composite_score,
            dimension_scores = EXCLUDED.dimension_scores,
            rank_position = EXCLUDED.rank_position,
            screening_reason = EXCLUDED.screening_reason,
            theme_info = EXCLUDED.theme_info
        """

        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    for item in results:
                        result_id = item.result_id or self._gen_id("result")
                        item.result_id = result_id
                        if not item.created_at:
                            item.created_at = datetime.now()

                        await conn.execute(
                            sql,
                            result_id,
                            item.strategy_id,
                            execution_id,
                            item.trade_date,
                            item.stock_id,
                            item.stock_name,
                            item.composite_score,
                            json.dumps(
                                {
                                    "mainline": item.dimension_scores.mainline,
                                    "cycle": item.dimension_scores.cycle,
                                    "leader": item.dimension_scores.leader,
                                    "technical": item.dimension_scores.technical,
                                },
                                ensure_ascii=False,
                            ),
                            item.rank_position,
                            item.screening_reason,
                            json.dumps(item.theme_info or {}, ensure_ascii=False),
                            item.created_at,
                        )
            return True
        except Exception as e:
            logger.error(f"保存选股结果失败: {e}")
            return False

    async def get_result(self, result_id: str) -> Optional[ScreeningResult]:
        """获取选股结果"""
        pool = await self._ensure_pool()
        sql = """
        SELECT result_id, strategy_id, trade_date, stock_id, stock_name,
               composite_score, dimension_scores, rank_position,
               screening_reason, theme_info, created_at
        FROM stock_screening_result
        WHERE result_id = $1
        """

        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(sql, result_id)
            if not row:
                return None

            return ScreeningResult(
                result_id=row["result_id"],
                strategy_id=row["strategy_id"],
                trade_date=row["trade_date"],
                stock_id=row["stock_id"],
                stock_name=row["stock_name"] or "",
                composite_score=float(row["composite_score"]),
                dimension_scores=self._to_dimension_scores(row["dimension_scores"]),
                rank_position=row["rank_position"],
                screening_reason=row["screening_reason"] or "",
                theme_info=self._parse_json(row["theme_info"], {}),
                created_at=row["created_at"],
            )
        except Exception as e:
            logger.error(f"获取选股结果失败 {result_id}: {e}")
            return None

    async def get_recent_results(
        self,
        strategy_id: Optional[str] = None,
        trade_date: Optional[date] = None,
        limit: int = 100,
    ) -> List[ScreeningResult]:
        """获取最近选股结果"""
        pool = await self._ensure_pool()
        sql = """
        SELECT result_id, strategy_id, trade_date, stock_id, stock_name,
               composite_score, dimension_scores, rank_position,
               screening_reason, theme_info, created_at
        FROM stock_screening_result
        WHERE ($1::text IS NULL OR strategy_id = $1)
          AND ($2::date IS NULL OR trade_date = $2)
        ORDER BY trade_date DESC, composite_score DESC
        LIMIT $3
        """
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, strategy_id, trade_date, limit)

            return [
                ScreeningResult(
                    result_id=row["result_id"],
                    strategy_id=row["strategy_id"],
                    trade_date=row["trade_date"],
                    stock_id=row["stock_id"],
                    stock_name=row["stock_name"] or "",
                    composite_score=float(row["composite_score"]),
                    dimension_scores=self._to_dimension_scores(row["dimension_scores"]),
                    rank_position=row["rank_position"],
                    screening_reason=row["screening_reason"] or "",
                    theme_info=self._parse_json(row["theme_info"], {}),
                    created_at=row["created_at"],
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(f"获取最近结果失败: {e}")
            return []

    async def save_llm_reviews(
        self,
        *,
        execution_id: str,
        strategy_id: str,
        trade_date: date,
        reviews: List[Dict[str, Any]],
    ) -> bool:
        """保存LLM复核结果。"""
        if not reviews:
            return True
        pool = await self._ensure_pool()
        sql = """
        INSERT INTO stock_screening_llm_review (
            review_id,
            execution_id,
            strategy_id,
            result_id,
            stock_id,
            trade_date,
            decision,
            llm_score,
            confidence,
            reasoning,
            risk_flags,
            evidence_refs,
            model_name,
            prompt_version,
            created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12::jsonb, $13, $14, $15
        )
        ON CONFLICT (result_id) DO UPDATE SET
            decision = EXCLUDED.decision,
            llm_score = EXCLUDED.llm_score,
            confidence = EXCLUDED.confidence,
            reasoning = EXCLUDED.reasoning,
            risk_flags = EXCLUDED.risk_flags,
            evidence_refs = EXCLUDED.evidence_refs,
            model_name = EXCLUDED.model_name,
            prompt_version = EXCLUDED.prompt_version
        """
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    for item in reviews:
                        await conn.execute(
                            sql,
                            self._gen_id("review"),
                            execution_id,
                            strategy_id,
                            item.get("result_id"),
                            item.get("stock_id", ""),
                            trade_date,
                            item.get("decision", "failed"),
                            item.get("llm_score"),
                            item.get("confidence"),
                            item.get("reasoning", ""),
                            json.dumps(item.get("risk_flags", []), ensure_ascii=False),
                            json.dumps(item.get("evidence_refs", []), ensure_ascii=False),
                            item.get("model_name", ""),
                            item.get("prompt_version", ""),
                            datetime.now(),
                        )
            return True
        except Exception as e:
            logger.error(f"保存LLM复核结果失败: {e}")
            return False

    async def get_llm_review(self, result_id: str) -> Optional[Dict[str, Any]]:
        pool = await self._ensure_pool()
        sql = """
        SELECT result_id, decision, llm_score, confidence, reasoning, risk_flags, evidence_refs, model_name, prompt_version, created_at
        FROM stock_screening_llm_review
        WHERE result_id = $1
        """
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(sql, result_id)
            if not row:
                return None
            return {
                "result_id": row["result_id"],
                "decision": row["decision"],
                "score": float(row["llm_score"] or 0),
                "confidence": float(row["confidence"] or 0),
                "reasoning": row["reasoning"] or "",
                "risk_flags": self._parse_json(row["risk_flags"], []),
                "evidence_refs": self._parse_json(row["evidence_refs"], []),
                "model_name": row["model_name"] or "",
                "review_version": row["prompt_version"] or "",
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
        except Exception as e:
            logger.error(f"获取LLM复核结果失败 {result_id}: {e}")
            return None

    async def get_llm_reviews_by_result_ids(self, result_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not result_ids:
            return {}
        pool = await self._ensure_pool()
        sql = """
        SELECT result_id, decision, llm_score, confidence, reasoning, risk_flags, evidence_refs, model_name, prompt_version, created_at
        FROM stock_screening_llm_review
        WHERE result_id = ANY($1::text[])
        """
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, result_ids)
            payload: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                payload[row["result_id"]] = {
                    "result_id": row["result_id"],
                    "decision": row["decision"],
                    "score": float(row["llm_score"] or 0),
                    "confidence": float(row["confidence"] or 0),
                    "reasoning": row["reasoning"] or "",
                    "risk_flags": self._parse_json(row["risk_flags"], []),
                    "evidence_refs": self._parse_json(row["evidence_refs"], []),
                    "model_name": row["model_name"] or "",
                    "review_version": row["prompt_version"] or "",
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
            return payload
        except Exception as e:
            logger.error(f"批量获取LLM复核结果失败: {e}")
            return {}

    async def create_execution(self, execution: ScreeningExecution) -> Optional[ScreeningExecution]:
        """创建选股执行记录"""
        pool = await self._ensure_pool()
        sql = """
        INSERT INTO stock_screening_execution (
            execution_id,
            strategy_id,
            trade_date,
            status,
            total_stocks,
            screened_stocks,
            results_count,
            execution_time_ms,
            error_message,
            created_at,
            completed_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """

        try:
            if not execution.execution_id:
                execution.execution_id = self._gen_id("exec")
            if not execution.created_at:
                execution.created_at = datetime.now()

            async with pool.acquire() as conn:
                await conn.execute(
                    sql,
                    execution.execution_id,
                    execution.strategy_id,
                    execution.trade_date,
                    execution.status,
                    execution.total_stocks,
                    execution.screened_stocks,
                    execution.results_count,
                    execution.execution_time_ms,
                    execution.error_message,
                    execution.created_at,
                    execution.completed_at,
                )
            return execution
        except Exception as e:
            logger.error(f"创建执行记录失败: {e}")
            return None

    async def update_execution(self, execution_id: str, updates: Dict[str, Any]) -> bool:
        """更新选股执行记录"""
        if not updates:
            return False

        pool = await self._ensure_pool()
        fields: List[str] = []
        values: List[Any] = []

        for key in (
            "status",
            "total_stocks",
            "screened_stocks",
            "results_count",
            "execution_time_ms",
            "error_message",
            "completed_at",
        ):
            if key in updates:
                fields.append(f"{key} = ${len(values) + 1}")
                values.append(updates[key])

        if not fields:
            return False

        values.append(execution_id)
        sql = f"""
        UPDATE stock_screening_execution
        SET {", ".join(fields)}
        WHERE execution_id = ${len(values)}
        """

        try:
            async with pool.acquire() as conn:
                result = await conn.execute(sql, *values)
            return result.upper().startswith("UPDATE 1")
        except Exception as e:
            logger.error(f"更新执行记录失败 {execution_id}: {e}")
            return False

    async def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """获取选股执行记录"""
        pool = await self._ensure_pool()
        sql = """
        SELECT
            execution_id,
            strategy_id,
            trade_date,
            status,
            total_stocks,
            screened_stocks,
            results_count,
            execution_time_ms,
            error_message,
            created_at,
            completed_at
        FROM stock_screening_execution
        WHERE execution_id = $1
        """
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(sql, execution_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"获取执行记录失败 {execution_id}: {e}")
            return None

    async def get_latest_execution(self, strategy_id: str, trade_date: date) -> Optional[Dict[str, Any]]:
        """获取策略在指定交易日最近一次执行记录"""
        pool = await self._ensure_pool()
        sql = """
        SELECT
            execution_id,
            strategy_id,
            trade_date,
            status,
            total_stocks,
            screened_stocks,
            results_count,
            execution_time_ms,
            error_message,
            created_at,
            completed_at
        FROM stock_screening_execution
        WHERE strategy_id = $1
          AND trade_date = $2::date
        ORDER BY created_at DESC
        LIMIT 1
        """
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(sql, strategy_id, trade_date)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"获取最近执行记录失败 {strategy_id}/{trade_date}: {e}")
            return None

    async def get_latest_snapshot_trade_date(self, on_or_before: date) -> Optional[date]:
        """获取小于等于给定日期的最近快照交易日。"""
        pool = await self._ensure_pool()
        sql = """
        SELECT MAX(trade_date) AS trade_date
        FROM subject_stock_daily_snapshot
        WHERE trade_date <= $1::date
        """
        try:
            async with pool.acquire() as conn:
                value = await conn.fetchval(sql, on_or_before)
            return value
        except Exception as e:
            logger.error(f"获取最近快照交易日失败 <= {on_or_before}: {e}")
            return None

    async def get_snapshot_stock_count(self, trade_date: date) -> int:
        """获取指定交易日快照中的去重股票数量。"""
        pool = await self._ensure_pool()
        sql = """
        SELECT COUNT(DISTINCT split_part(stock_id, '.', 1))
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
          AND stock_id IS NOT NULL
          AND stock_id <> ''
        """
        try:
            async with pool.acquire() as conn:
                value = await conn.fetchval(sql, trade_date)
            return int(value or 0)
        except Exception as e:
            logger.error(f"获取快照股票数量失败 {trade_date}: {e}")
            return 0

    async def get_user_favorites(self, user_id: str) -> List[UserFavorite]:
        """获取用户收藏"""
        pool = await self._ensure_pool()
        sql = """
        SELECT favorite_id, user_id, result_id, notes, tags, created_at
        FROM user_stock_screening_favorite
        WHERE user_id = $1
        ORDER BY created_at DESC
        """

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, user_id)
            return [
                UserFavorite(
                    favorite_id=row["favorite_id"],
                    user_id=row["user_id"],
                    result_id=row["result_id"],
                    notes=row["notes"],
                    tags=self._parse_json(row["tags"], []),
                    created_at=row["created_at"],
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(f"获取用户收藏失败 {user_id}: {e}")
            return []

    async def add_favorite(self, favorite: UserFavorite) -> bool:
        """添加用户收藏"""
        pool = await self._ensure_pool()
        sql = """
        INSERT INTO user_stock_screening_favorite (
            favorite_id, user_id, result_id, notes, tags, created_at
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
        ON CONFLICT (user_id, result_id) DO UPDATE SET
            notes = EXCLUDED.notes,
            tags = EXCLUDED.tags,
            created_at = EXCLUDED.created_at
        """

        try:
            if not favorite.favorite_id:
                favorite.favorite_id = self._gen_id("fav")
            if not favorite.created_at:
                favorite.created_at = datetime.now()

            async with pool.acquire() as conn:
                await conn.execute(
                    sql,
                    favorite.favorite_id,
                    favorite.user_id,
                    favorite.result_id,
                    favorite.notes,
                    json.dumps(favorite.tags or [], ensure_ascii=False),
                    favorite.created_at,
                )
            return True
        except Exception as e:
            logger.error(f"添加收藏失败: {e}")
            return False

    async def update_favorite(self, favorite_id: str, notes: Optional[str], tags: Optional[List[str]]) -> bool:
        """更新收藏备注与标签"""
        pool = await self._ensure_pool()
        sql = """
        UPDATE user_stock_screening_favorite
        SET notes = $1,
            tags = $2::jsonb
        WHERE favorite_id = $3
        """
        try:
            async with pool.acquire() as conn:
                result = await conn.execute(
                    sql,
                    notes,
                    json.dumps(tags or [], ensure_ascii=False),
                    favorite_id,
                )
            return result.upper().startswith("UPDATE 1")
        except Exception as e:
            logger.error(f"更新收藏失败 {favorite_id}: {e}")
            return False

    async def remove_favorite(self, favorite_id: str) -> bool:
        """移除用户收藏"""
        pool = await self._ensure_pool()
        sql = "DELETE FROM user_stock_screening_favorite WHERE favorite_id = $1"
        try:
            async with pool.acquire() as conn:
                result = await conn.execute(sql, favorite_id)
            return result.upper().startswith("DELETE 1")
        except Exception as e:
            logger.error(f"移除收藏失败 {favorite_id}: {e}")
            return False

    async def get_statistics(
        self,
        strategy_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        """获取选股统计"""
        pool = await self._ensure_pool()

        sql_base = """
        SELECT
            COUNT(*)::bigint AS total_results,
            COALESCE(AVG(composite_score), 0)::float8 AS avg_score
        FROM stock_screening_result
        WHERE ($1::text IS NULL OR strategy_id = $1)
          AND ($2::date IS NULL OR trade_date >= $2)
          AND ($3::date IS NULL OR trade_date <= $3)
        """

        sql_themes = """
        SELECT
            COALESCE(theme_info->>'subject_key', '') AS subject_key,
            COUNT(*)::bigint AS count
        FROM stock_screening_result
        WHERE theme_info IS NOT NULL
          AND ($1::text IS NULL OR strategy_id = $1)
          AND ($2::date IS NULL OR trade_date >= $2)
          AND ($3::date IS NULL OR trade_date <= $3)
        GROUP BY COALESCE(theme_info->>'subject_key', '')
        HAVING COALESCE(theme_info->>'subject_key', '') <> ''
        ORDER BY count DESC
        LIMIT 10
        """

        score_distribution = []

        try:
            async with pool.acquire() as conn:
                base_row = await conn.fetchrow(sql_base, strategy_id, date_from, date_to)
                theme_rows = await conn.fetch(sql_themes, strategy_id, date_from, date_to)

                for min_score in range(0, 100, 10):
                    max_score = 100 if min_score == 90 else min_score + 9
                    sql_dist = """
                    SELECT COUNT(*)::bigint
                    FROM stock_screening_result
                    WHERE composite_score >= $1
                      AND composite_score <= $2
                      AND ($3::text IS NULL OR strategy_id = $3)
                      AND ($4::date IS NULL OR trade_date >= $4)
                      AND ($5::date IS NULL OR trade_date <= $5)
                    """
                    count = await conn.fetchval(
                        sql_dist,
                        min_score,
                        max_score,
                        strategy_id,
                        date_from,
                        date_to,
                    )
                    score_distribution.append(
                        {
                            "score_range": f"{min_score}-{max_score}",
                            "count": int(count or 0),
                        }
                    )

            base_data = dict(base_row) if base_row else {}
            return {
                "total_results": int(base_data.get("total_results", 0)),
                "avg_composite_score": float(base_data.get("avg_score", 0.0)),
                "top_themes": [
                    {"subject_key": row["subject_key"], "count": int(row["count"])}
                    for row in theme_rows
                ],
                "score_distribution": score_distribution,
            }
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {
                "total_results": 0,
                "avg_composite_score": 0.0,
                "top_themes": [],
                "score_distribution": [],
            }

    async def delete_strategy(self, strategy_id: str) -> bool:
        """删除策略（软删除）"""
        pool = await self._ensure_pool()
        sql = """
        UPDATE stock_screening_strategy
        SET is_active = false,
            updated_at = NOW()
        WHERE strategy_id = $1
        """
        try:
            async with pool.acquire() as conn:
                result = await conn.execute(sql, strategy_id)
            return result.upper().startswith("UPDATE 1")
        except Exception as e:
            logger.error(f"删除策略失败 {strategy_id}: {e}")
            return False

    async def query_history(
        self,
        strategy_id: Optional[str] = None,
        trade_date_from: Optional[date] = None,
        trade_date_to: Optional[date] = None,
        stock_id: Optional[str] = None,
        min_score: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """按条件查询历史结果"""
        pool = await self._ensure_pool()
        sql_base = """
        FROM stock_screening_result
        WHERE ($1::text IS NULL OR strategy_id = $1)
          AND ($2::date IS NULL OR trade_date >= $2)
          AND ($3::date IS NULL OR trade_date <= $3)
          AND ($4::text IS NULL OR split_part(stock_id, '.', 1) = split_part($4, '.', 1))
          AND ($5::float8 IS NULL OR composite_score >= $5)
        """
        sql_count = "SELECT COUNT(*)::bigint " + sql_base
        sql_rows = """
        SELECT
            result_id,
            strategy_id,
            trade_date,
            stock_id,
            stock_name,
            composite_score,
            dimension_scores,
            rank_position,
            screening_reason,
            theme_info,
            created_at
        """ + sql_base + """
        ORDER BY trade_date DESC, composite_score DESC, created_at DESC
        LIMIT $6 OFFSET $7
        """

        try:
            async with pool.acquire() as conn:
                total_count = await conn.fetchval(
                    sql_count,
                    strategy_id,
                    trade_date_from,
                    trade_date_to,
                    stock_id,
                    min_score,
                )
                rows = await conn.fetch(
                    sql_rows,
                    strategy_id,
                    trade_date_from,
                    trade_date_to,
                    stock_id,
                    min_score,
                    limit,
                    offset,
                )

            items = []
            for row in rows:
                theme_info = self._parse_json(row["theme_info"], {})
                items.append(
                    {
                        "result_id": row["result_id"],
                        "stock_id": row["stock_id"],
                        "stock_name": row["stock_name"],
                        "composite_score": float(row["composite_score"]),
                        "dimension_scores": self._parse_json(row["dimension_scores"], {}),
                        "rank_position": row["rank_position"],
                        "screening_reason": row["screening_reason"] or "",
                        "theme_info": theme_info or None,
                        "trade_date": row["trade_date"].isoformat() if row["trade_date"] else None,
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    }
                )

            return {
                "results": items,
                "total_count": int(total_count or 0),
                "has_more": offset + len(items) < int(total_count or 0),
            }
        except Exception as e:
            logger.error(f"查询历史结果失败: {e}")
            return {"results": [], "total_count": 0, "has_more": False}
