"""P3-1: SourceAdapter 基类。

定义统一数据源适配接口：name / source_type / start / stop / health。
子类只需实现 fetch / normalize_minimal / publish 三个核心方法。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class SourceAdapter(ABC):
    """数据源适配器基类。

    每个子类封装一个数据源的采集 → 标准化 → 发布流程，
    输出带 envelope 的消息到对应 Redis Stream。
    """

    name: str = ""
    source_type: str = "unknown"

    # ---- 子类必须实现 ----

    @abstractmethod
    async def fetch(self) -> List[Dict]:
        """采集原始数据。返回原始 dict 列表。"""
        ...

    @abstractmethod
    def normalize_minimal(self, raw_items: List[Dict]) -> List[Dict]:
        """最小标准化：补齐 source_type / source_name / collector_name 等元数据。"""
        ...

    @abstractmethod
    async def publish(self, items: List[Dict]) -> int:
        """发布到目标 stream，每条消息带 envelope 包装。返回发布条数。"""
        ...

    # ---- 生命周期（子类可按需覆盖） ----

    async def start(self) -> None:
        """启动适配器（建立连接、预热资源等）。"""
        pass

    async def stop(self) -> None:
        """停止适配器（释放连接、清理资源等）。"""
        pass

    async def health(self) -> dict:
        """返回适配器健康状态。"""
        return {
            "adapter": self.name,
            "source_type": self.source_type,
            "status": "unknown",
        }

    # ---- 辅助 ----

    def _adapter_meta(self) -> Dict[str, Any]:
        """返回适配器元信息，供子类在消息中附加。"""
        return {
            "adapter_name": self.name,
            "source_type": self.source_type,
        }
