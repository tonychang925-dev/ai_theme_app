"""P1-2: Stream 命名统一与 Alias 映射。

迁移四步法：Alias → 双写 → 切读 → 废弃
第一阶段：新名字 → 映射到旧名字（旧代码继续读旧 stream，不产生断链）
"""
from __future__ import annotations

# 新名字 → 旧名字
STREAM_ALIASES: dict[str, str] = {
    "stream:intel.raw.news": "stream:news:raw",
    "stream:intel.event.structured": "stream:events:structured",
    "stream:alert.decision": "stream:events:decision",
    "stream:ui.feed": "stream:event:feed",
}

# 反向映射（方便查询）
OLD_TO_NEW: dict[str, str] = {v: k for k, v in STREAM_ALIASES.items()}


def resolve(stream_name: str) -> str:
    """将新名字解析为实际 Redis key。

    - 如果是新名字且在 alias 表中 → 返回旧名字（第一阶段）
    - 如果是旧名字 → 直接返回（兼容）
    - 未知名字 → 原样返回
    """
    return STREAM_ALIASES.get(stream_name, stream_name)


def canonical(stream_name: str) -> str:
    """返回规范名称（优先新名字）。"""
    return OLD_TO_NEW.get(stream_name, stream_name)
