"""Token 提供器 — 读取 /tmp/jyhf_auth_token.json，校验有效性."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("sps.jyhf_market.token_provider")


class JyhfTokenProvider:
    """从 CDP hook 写入的 JSON 文件读取 JWT，通过轻量 API 调用校验。"""

    def __init__(self, token_path: str, validation_endpoint: str, api_base_url: str, timeout: float = 10.0):
        self._token_path = Path(token_path)
        self._validation_url = f"{api_base_url.rstrip('/')}{validation_endpoint}"
        self._timeout = timeout
        self._cached_token: str | None = None
        self._cached_at: float = 0.0
        self._cache_ttl: float = 300.0

    def get_token(self) -> str:
        if self._cached_token and (time.time() - self._cached_at) < self._cache_ttl:
            return self._cached_token
        token = self._load_from_file()
        if token and self._validate(token):
            self._cached_token = token
            self._cached_at = time.time()
            return token
        raise RuntimeError("JYHF token unavailable")

    def is_token_valid(self) -> bool:
        try:
            self.get_token()
            return True
        except RuntimeError:
            return False

    def force_refresh(self) -> bool:
        self._cached_token = None
        token = self._load_from_file()
        if token and self._validate(token):
            self._cached_token = token
            self._cached_at = time.time()
            return True
        return False

    def _load_from_file(self) -> Optional[str]:
        try:
            data = json.loads(self._token_path.read_text())
            token = data.get("token")
            if token:
                logger.debug("Token loaded from %s", self._token_path)
                return token
        except Exception as exc:
            logger.warning("Token file read error: %s", exc)
        return None

    def _validate(self, token: str) -> bool:
        try:
            r = httpx.get(
                self._validation_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self._timeout,
            )
            return r.status_code == 200
        except Exception as exc:
            logger.warning("Token validation error: %s", exc)
            return False
