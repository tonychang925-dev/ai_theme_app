"""P1-D: PDF 正文解析器。

从 cninfo PDF URL 下载并提取正文文本，更新 raw_intel_document。
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

CNINFO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "http://www.cninfo.com.cn/",
}

DEFAULT_CACHE_DIR = Path("data/intel_pdfs")
MAX_PDF_MB = 20
DOWNLOAD_TIMEOUT = 20
MAX_CONTENT_CHARS = 12000


class PdfContentExtractor:
    """PDF 下载 + 正文提取 + 清洗。"""

    def __init__(
        self,
        *,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        max_pdf_mb: int = MAX_PDF_MB,
        download_timeout: int = DOWNLOAD_TIMEOUT,
        max_content_chars: int = MAX_CONTENT_CHARS,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_pdf_bytes = max_pdf_mb * 1024 * 1024
        self.download_timeout = download_timeout
        self.max_content_chars = max_content_chars

    def process(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """处理单条 raw_intel_document，返回更新字段 dict。"""
        doc_id = doc["id"]
        pdf_url = (doc.get("pdf_url") or "").strip()
        source_system = doc.get("source_system", "cninfo")

        result = {
            "doc_id": doc_id,
            "content_text": "",
            "pdf_path": "",
            "parse_status": "raw",
            "parse_method": None,
            "parse_error": None,
        }

        if not pdf_url:
            result["parse_status"] = "skipped_no_url"
            return result

        # 1. Download
        pdf_bytes = self._download(pdf_url)
        if pdf_bytes is None:
            result["parse_status"] = "download_failed"
            result["parse_error"] = "download failed or too large"
            return result

        # 2. Save to cache
        pdf_path = self._cache_path(source_system, doc_id, pdf_url)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)

        # 3. Extract text via toolchain
        text, method = self._extract_text(pdf_path)
        if not text or len(text) < 50:
            result["parse_status"] = "parse_failed"
            result["parse_error"] = f"extracted text too short (method={method})"
            result["pdf_path"] = str(pdf_path)
            return result

        # 4. Clean + truncate
        text = _clean_text(text)
        text = text[:self.max_content_chars]

        result["content_text"] = text
        result["pdf_path"] = str(pdf_path)
        result["parse_status"] = "parsed"
        result["parse_method"] = method
        result["parse_error"] = None
        return result

    def _download(self, url: str) -> bytes | None:
        """下载 PDF，带重试和大小限制。"""
        for attempt in range(2):
            try:
                resp = requests.get(
                    url, headers=CNINFO_HEADERS,
                    timeout=self.download_timeout, stream=True,
                )
                if resp.status_code != 200:
                    logger.warning("PDF download HTTP %s for %s (attempt %s)", resp.status_code, url[:80], attempt + 1)
                    if attempt == 0:
                        time.sleep(2)
                    continue

                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_content(chunk_size=8192):
                    total += len(chunk)
                    if total > self.max_pdf_bytes:
                        logger.warning("PDF too large (%s bytes) for %s", total, url[:80])
                        return None
                    chunks.append(chunk)

                return b"".join(chunks)
            except requests.RequestException as exc:
                logger.warning("PDF download error for %s: %s (attempt %s)", url[:80], exc, attempt + 1)
                if attempt == 0:
                    time.sleep(2)

        return None

    def _extract_text(self, pdf_path: Path) -> tuple[str, str]:
        """工具链 fallback: pdftotext → pdfplumber → pypdf。返回 (text, method)。"""
        extractors: list[tuple[str, callable]] = [
            ("pdftotext", _by_pdftotext),
            ("pdfplumber", _by_pdfplumber),
            ("pypdf", _by_pypdf),
        ]
        for method_name, fn in extractors:
            try:
                text = fn(pdf_path)
                if text and len(text.strip()) >= 100:
                    return text, method_name
            except Exception as exc:
                logger.debug("%s failed for %s: %s", method_name, pdf_path.name, exc)
        return "", "failed"

    def _cache_path(self, source_system: str, doc_id: int, pdf_url: str) -> Path:
        url_hash = hashlib.md5(pdf_url.encode()).hexdigest()[:8]
        return self.cache_dir / source_system / f"{doc_id}_{url_hash}.pdf"


# ── Extractors ────────────────────────────────────────────────────────

def _by_pdftotext(pdf_path: Path) -> str:
    """pdftotext CLI (Poppler) — 最快最稳。"""
    import subprocess
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext exit={result.returncode}")
    return result.stdout


def _by_pdfplumber(pdf_path: Path) -> str:
    import pdfplumber
    with pdfplumber.open(str(pdf_path)) as pdf:
        parts = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


def _by_pypdf(pdf_path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    return "\n".join(parts)


def _clean_text(text: str) -> str:
    """简单清洗公告 PDF 正文。"""
    # 去除连续空白行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 去除表头/页脚常见噪声
    text = re.sub(r"^\s*证券代码[：:].*?\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*公告编号[：:].*?\n", "", text, flags=re.MULTILINE)
    # 去除多余空格
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
