from __future__ import annotations

import os
from typing import Any

import requests


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClientAdapter:
    def __init__(self, token: str, *, timeout: float = 30.0) -> None:
        if not token:
            raise ValueError("missing NOTION_TOKEN")
        self._token = token
        self._timeout = timeout

    @classmethod
    def from_env(cls) -> "NotionClientAdapter":
        return cls(token=os.getenv("NOTION_TOKEN", "").strip())

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = requests.request(
            method.upper(),
            f"{NOTION_API_BASE}{path}",
            headers=self._headers(),
            json=body,
            timeout=self._timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Notion API failed: status={resp.status_code}, body={resp.text}")
        data = resp.json()
        return data if isinstance(data, dict) else {}

    def query_database(self, database_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"/databases/{database_id}/query", body=body)

    def retrieve_block_children(self, block_id: str, *, start_cursor: str | None = None) -> dict[str, Any]:
        query = f"?start_cursor={start_cursor}" if start_cursor else ""
        return self.request("GET", f"/blocks/{block_id}/children{query}")

    def append_children(self, block_id: str, children: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("PATCH", f"/blocks/{block_id}/children", body={"children": children})

    def update_page_properties(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", f"/pages/{page_id}", body={"properties": properties})

