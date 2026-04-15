"""
选股器SQLAlchemy数据库模型
"""

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean,
    DateTime, Date, JSON, DECIMAL, ForeignKey, Index, CheckConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

Base = declarative_base()


class StockScreeningStrategy(Base):
    """选股策略表"""
    __tablename__ = 'stock_screening_strategy'

    strategy_id = Column(String(64), primary_key=True)
    strategy_name = Column(String(128), nullable=False)
    strategy_type = Column(String(32), nullable=False)
    description = Column(Text)
    weight_config = Column(JSONB, nullable=False)
    filter_config = Column(JSONB, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    created_by = Column(String(64))
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint(
            "strategy_type IN ('mainline', 'cycle', 'leader', 'technical', 'composite')",
            name='chk_strategy_type'
        ),
        CheckConstraint(
            "weight_config ? 'mainline' AND weight_config ? 'cycle' AND weight_config ? 'leader' AND weight_config ? 'technical'",
            name='chk_weight_config'
        ),
        Index('idx_screening_strategy_active', 'is_active'),
    )


class StockScreeningExecution(Base):
    """选股执行记录表"""
    __tablename__ = 'stock_screening_execution'

    execution_id = Column(String(64), primary_key=True)
    strategy_id = Column(String(64), ForeignKey('stock_screening_strategy.strategy_id'), nullable=False)
    trade_date = Column(Date, nullable=False)
    status = Column(String(32), nullable=False)
    total_stocks = Column(Integer, default=0)
    screened_stocks = Column(Integer, default=0)
    results_count = Column(Integer, default=0)
    execution_time_ms = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    completed_at = Column(DateTime)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name='chk_execution_status'
        ),
        Index('idx_execution_strategy_date', 'strategy_id', 'trade_date'),
        Index('idx_execution_status', 'status', 'created_at'),
    )


class StockScreeningResult(Base):
    """选股结果表"""
    __tablename__ = 'stock_screening_result'

    result_id = Column(String(64), primary_key=True)
    strategy_id = Column(String(64), ForeignKey('stock_screening_strategy.strategy_id'), nullable=False)
    execution_id = Column(String(64), ForeignKey('stock_screening_execution.execution_id'), nullable=False)
    trade_date = Column(Date, nullable=False)
    stock_id = Column(String(32), nullable=False)
    stock_name = Column(String(64))
    composite_score = Column(DECIMAL(5, 2), nullable=False)
    dimension_scores = Column(JSONB, nullable=False)
    rank_position = Column(Integer)
    screening_reason = Column(Text)
    theme_info = Column(JSONB)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        CheckConstraint(
            "composite_score >= 0 AND composite_score <= 100",
            name='chk_composite_score_range'
        ),
        CheckConstraint(
            "dimension_scores ? 'mainline' AND dimension_scores ? 'cycle' AND dimension_scores ? 'leader' AND dimension_scores ? 'technical'",
            name='chk_dimension_scores'
        ),
        Index('idx_result_strategy_date', 'strategy_id', 'trade_date', 'composite_score'),
        Index('idx_result_stock', 'stock_id', 'trade_date'),
        Index('idx_result_composite_score', 'composite_score'),
        Index('idx_result_execution', 'execution_id'),
        Index('idx_screening_result_theme_info', 'theme_info', postgresql_using='gin'),
        Index('idx_screening_result_dimension_scores', 'dimension_scores', postgresql_using='gin'),
    )


class UserStockScreeningFavorite(Base):
    """用户选股收藏表"""
    __tablename__ = 'user_stock_screening_favorite'

    favorite_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False)
    result_id = Column(String(64), ForeignKey('stock_screening_result.result_id'), nullable=False)
    notes = Column(Text)
    tags = Column(JSONB)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index('idx_favorite_user', 'user_id', 'created_at'),
        Index('idx_favorite_result', 'result_id'),
    )