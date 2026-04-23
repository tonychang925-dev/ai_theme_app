from __future__ import annotations

from typing import Any, Awaitable, Callable

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class RedisEventBusGateway:
    """Adapter for Redis Stream publishing/subscribing."""

    def __init__(self, stream_gateway: Any) -> None:
        self._stream = stream_gateway

    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        if self._stream is None:
            return ""
        message_id = await self._stream.publish_to_stream(topic, payload)
        return str(message_id or "")

    async def subscribe(self, topic: str, handler: EventHandler, consumer_group: str) -> None:
        if self._stream is None:
            return
        await self._stream.subscribe(topic=topic, handler=handler, consumer_group=consumer_group)
