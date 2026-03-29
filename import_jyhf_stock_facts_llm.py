#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
批量从 theme_data_complete/stock_details/*.json 中提取 stock_facts（LLM版）并落库。

支持：
1. 处理前统计股票信息
2. 批量处理 stock_facts 提取和数据库写入
3. 缓存处理（避免重复调用 LLM）
4. 断点续跑（processed 标记）
5. 处理后全量校验
6. tqdm 进度条显示
7. 宽松 JSON 解析（修复常见格式错误）
8. 失败股票清单输出
9. 支持按失败清单重跑
10. 支持 fail-fast 模式

说明：
- 只处理 stock_facts
- 不重复处理 stocks / stock_lightspots
- 使用 LLM 做 schema-first 结构化抽取
"""

import os
import sys
import json
import time
import re
import argparse
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime

import asyncpg
import requests
from tqdm import tqdm

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =========================
# 常量配置
# =========================

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

FACT_TYPES = [
    "main_business",
    "industry_role",
    "product",
    "technology",
    "customer",
    "benefit_logic",
]

STOCK_FACT_EXTRACT_SYSTEM = """你是一个股票画像结构化事实抽取器。
你的任务是从上市公司详情文本中，提取可用于“题材树-股票映射”的结构化事实。

目标：
输出能够支撑“题材树 -> 分支/叶子 -> 股票映射”的短语级事实，而不是摘要、评论或长句解释。

硬性要求：
1. 只抽取文本中明确表达、能被原文直接支撑的事实，不得编造，不得意译过度。
2. 输出必须落在给定 fact_type 枚举中，不允许新增类型。
3. fact_value 必须尽量“原子化”：
   - 能拆开的并列项必须拆开成多条；
   - 不要把多个业务/产品/客户合并成一条。
4. fact_value 必须是“短语级表达”，优先名词短语，不要输出完整句子、解释句、结论句。
5. evidence_span 必须是能直接支撑该事实的原文片段，尽量短，不要整段复制。
6. 不要抽取短期行情信息、媒体表述、宣传口号、空泛评价。
7. 若某类事实不存在，可以不输出；宁缺毋滥。
8. 同一 fact_type 下不要重复表达高度相近的事实。

允许的 fact_type 只有：
- main_business
- industry_role
- product
- technology
- customer
- benefit_logic

各 fact_type 定义：
1. main_business
   - 公司主营业务板块 / 主要业务方向
   - 应输出板块名或业务方向短语
   - 例如：存储半导体、高端制造、计量智能终端
   - 若原文是并列表达，必须拆成多条

2. industry_role
   - 公司在产业链中的角色、行业定位、身份标签
   - 例如：存储封测企业、EMS企业、硬盘磁头制造商
   - 不要把具体产品放进 industry_role

3. product
   - 公司销售/提供的产品、服务、解决方案、器件类别
   - 例如：智能电表、SSD、硅基片制造、高端存储芯片封装测试
   - 不要把纯技术工艺放进 product

4. technology
   - 公司具备的关键技术、封装工艺、量产能力、测试能力、技术平台
   - 例如：8层堆叠、FlipChip芯片封装、LPDDR4/X封测服务、3D NAND量产
   - 不要把泛泛业务板块放进 technology

5. customer
   - 明确的客户、合作绑定对象、供应对象
   - fact_value 优先输出“客户/对象名称”或简洁对象短语
   - 例如：金士顿科技、全球三大硬盘厂商
   - 不要输出“为某某提供服务”这类整句

6. benefit_logic
   - 与题材映射相关的受益逻辑、受益方向、映射标签
   - 必须是原文或亮点中明确表达的逻辑，不可自行推断
   - 例如：存储国产化、国产替代
   - 这是弱事实，只有在文本有明确支撑时才输出

负面要求：
- 不要输出“有望受益”“空间广阔”“成长性强”“龙头潜力大”等空泛表述
- 不要输出完整叙述句
- 不要输出日期、涨跌幅、金额、市场行情
- 不要把同一个意思换几种说法重复输出

输出 JSON 格式：
{
  "facts": [
    {
      "fact_type": "product",
      "fact_value": "DRAM封装测试",
      "evidence_span": "主要从事高端存储芯片的封装与测试"
    },
    {
      "fact_type": "customer",
      "fact_value": "金士顿科技",
      "evidence_span": "与美国金士顿科技公司展开深度合作"
    }
  ]
}
"""


# =========================
# 数据库管理类（只修复 acquire 方法）
# =========================

class PostgresManager:
    """PostgreSQL连接管理器 - 修复异步上下文管理器问题"""
    
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        """创建连接池"""
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        logger.info(f"✅ PostgreSQL连接成功")

    async def disconnect(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL连接已关闭")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.disconnect()

    async def acquire(self):
        """获取连接 - 使用 pool.acquire() 而不是 __aenter__"""
        if not self.pool:
            raise RuntimeError("连接池未初始化，请先调用 connect()")
        return await self.pool.acquire()  # 修复这里：使用 acquire() 而不是 __aenter__

    async def release(self, conn):
        """释放连接"""
        if self.pool:
            await self.pool.release(conn)  # 修复这里：使用 release() 而不是 __aexit__


def get_postgres_config():
    """获取PostgreSQL配置"""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "zxbzj~925")
    database = os.getenv("POSTGRES_DATABASE", "stock_data_test")
    
    dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return PostgresManager(dsn)


# =========================
# DeepSeek客户端（完全保留您的代码）
# =========================

class DeepSeekClient:
    """DeepSeek API客户端，支持JSON修复"""
    
    def __init__(self, api_key: str, base_url: str = DEEPSEEK_BASE_URL, model: str = DEEPSEEK_MODEL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.sess = requests.Session()
        # 添加重试适配器
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        self.sess.mount('http://', adapter)
        self.sess.mount('https://', adapter)

    @staticmethod
    def _repair_json(text: str) -> str:
        """尝试修复常见的JSON格式错误"""
        if not text:
            return text
        
        # 修复1: 在 "}" 或 "]" 前缺少逗号的情况
        repaired = re.sub(r'(\S)\s*\n\s*\}', r'\1\n}', text)
        repaired = re.sub(r'(\S)\s*\n\s*\]', r'\1\n]', repaired)
        
        # 修复2: 在对象间缺少逗号的情况: } {  ->  }, {
        repaired = re.sub(r'\}\s*\{', '},{', repaired)
        
        # 修复3: 在数组元素间缺少逗号的情况: ] [  ->  ], [
        repaired = re.sub(r'\]\s*\[', '],[', repaired)
        
        # 修复4: 在字符串后缺少逗号: "value"\n"next"  ->  "value",\n"next"
        repaired = re.sub(r'"\s*\n\s*"', '",\n"', repaired)
        
        # 修复5: 多余逗号在数组或对象末尾
        repaired = re.sub(r',\s*}', '}', repaired)
        repaired = re.sub(r',\s*\]', ']', repaired)
        
        # 修复6: 修复缺失的引号
        repaired = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', repaired)
        
        return repaired

    @staticmethod
    def _extract_json_block_loose(text: str) -> Optional[str]:
        """宽松提取JSON块"""
        if not text:
            return None
        
        # 先尝试直接提取
        t = text.strip()
        if t.startswith("{") and t.endswith("}"):
            return t
        
        # 用正则提取第一个大括号块
        m = re.search(r"(\{[\s\S]*\})", t)
        if m:
            return m.group(1).strip()
        
        # 尝试提取可能被包裹的JSON
        m = re.search(r'```json\s*([\s\S]*?)\s*```', t)
        if m:
            return m.group(1).strip()
        
        return None

    def run_json_object(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 16000,  # 增加到16000避免截断
        temperature: float = 0.1,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """调用DeepSeek API并返回JSON对象"""
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_err = None
        backoff = 2.0

        for attempt in range(max_retries + 1):
            try:
                logger.debug(f"API调用尝试 {attempt+1}/{max_retries+1}")
                resp = self.sess.post(url, headers=headers, json=payload, timeout=(10, 120))

                # 处理限流和服务器错误
                if resp.status_code == 429:
                    wait_time = backoff * 2
                    logger.warning(f"触发限流，等待 {wait_time:.1f}秒")
                    time.sleep(wait_time)
                    backoff = min(backoff * 2, 30)
                    continue
                    
                if resp.status_code >= 500:
                    logger.warning(f"服务器错误 {resp.status_code}，等待 {backoff:.1f}秒")
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, 30)
                    continue

                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]

                # 尝试多种方式解析JSON
                obj = None
                parse_errors = []

                # 方式1：直接解析
                try:
                    obj = json.loads(content)
                    logger.debug("直接解析成功")
                except json.JSONDecodeError as e:
                    parse_errors.append(f"直接解析失败: {e}")
                    pass

                # 方式2：提取JSON块
                if obj is None:
                    block = self._extract_json_block_loose(content)
                    if block:
                        try:
                            obj = json.loads(block)
                            logger.debug("JSON块解析成功")
                        except json.JSONDecodeError as e:
                            parse_errors.append(f"JSON块解析失败: {e}")
                            pass

                # 方式3：修复后解析
                if obj is None:
                    repaired = self._repair_json(content)
                    try:
                        obj = json.loads(repaired)
                        logger.debug("修复后解析成功")
                    except json.JSONDecodeError as e:
                        parse_errors.append(f"修复后解析失败: {e}")
                        pass

                # 方式4：尝试提取facts数组
                if obj is None:
                    # 尝试找到facts数组
                    facts_match = re.search(r'"facts"\s*:\s*(\[[\s\S]*?\])', content)
                    if facts_match:
                        facts_str = facts_match.group(1)
                        try:
                            facts = json.loads(facts_str)
                            obj = {"facts": facts}
                            logger.debug("facts数组提取成功")
                        except:
                            pass

                if obj is None:
                    # 记录错误内容以便调试
                    error_msg = f"JSON解析失败，尝试了{len(parse_errors)}种方法"
                    logger.error(f"{error_msg}")
                    for i, err in enumerate(parse_errors):
                        logger.error(f"  方法{i+1}: {err}")
                    logger.error(f"内容预览: {content[:500]}")
                    raise json.JSONDecodeError(f"无法解析LLM输出: {error_msg}", content, 0)

                # 确保返回的是字典
                if isinstance(obj, list):
                    obj = {"facts": obj}

                if not isinstance(obj, dict):
                    obj = {"facts": []}

                # 验证facts字段
                if "facts" not in obj:
                    obj["facts"] = []
                elif not isinstance(obj["facts"], list):
                    obj["facts"] = [obj["facts"]] if obj["facts"] else []

                return obj

            except requests.exceptions.RequestException as e:
                last_err = e
                logger.warning(f"请求失败 (尝试 {attempt+1}/{max_retries+1}): {e}")
                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, 30)

            except Exception as e:
                last_err = e
                logger.warning(f"处理失败 (尝试 {attempt+1}/{max_retries+1}): {type(e).__name__}: {e}")
                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, 30)

        raise RuntimeError(f"LLM 调用失败，已重试{max_retries}次: {repr(last_err)}")


# =========================
# 工具函数（完全保留您的代码）
# =========================

def read_json(path: Path) -> Any:
    """读取JSON文件"""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"JSON 解析失败 {path}: {e}")
        return {}


def strip_html_tags(html: str) -> str:
    """去除HTML标签"""
    if not html:
        return ""
    # 替换br标签为换行
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    # 移除其他HTML标签
    text = re.sub(r"<[^>]+>", "", text)
    # 合并多个换行
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def truncate_text(text: str, max_chars: int = 8000) -> str:
    """截断文本"""
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[内容已截断]"


def build_stock_fact_prompt(stock_data: Dict[str, Any]) -> str:
    """构建提示词"""
    stock_id = str(stock_data.get("stockId") or "").strip()
    name = str(stock_data.get("name") or "").strip()
    remark = str(stock_data.get("remark") or "").strip()
    detail_html = str(stock_data.get("detail") or "").strip()
    detail_text = strip_html_tags(detail_html)

    lightspots = []
    for x in stock_data.get("stockLightspots", []) or []:
        if isinstance(x, dict):
            c = str(x.get("content") or "").strip()
            if c:
                lightspots.append(c)

    lightspots_text = "\n".join([f"- {x}" for x in lightspots[:15]])

    return f"""股票代码：{stock_id}
股票名称：{name}

一句话定位（remark）：
{remark or "无"}

亮点句（lightspots）：
{lightspots_text or "无"}

公司详情正文：
{truncate_text(detail_text, 8000)}
"""


def split_main_business(text: str) -> List[str]:
    """拆分主营业务"""
    if not text:
        return []
    parts = re.split(r"[、，,和及与/]+", text)
    out = []
    for p in parts:
        p = p.strip("：:；;，,。 ")
        if p and len(p) <= 30:  # 限制长度
            out.append(p)
    return out


def normalize_llm_facts(obj: Dict[str, Any]) -> List[Dict[str, str]]:
    """规范化LLM输出的事实"""
    facts = obj.get("facts", [])
    if not isinstance(facts, list):
        return []

    out = []
    seen = set()

    for x in facts:
        if not isinstance(x, dict):
            continue
            
        fact_type = str(x.get("fact_type") or "").strip()
        fact_value = str(x.get("fact_value") or "").strip()
        evidence_span = str(x.get("evidence_span") or "").strip()

        if fact_type not in FACT_TYPES:
            continue
        if not fact_value or not evidence_span:
            continue
        if len(fact_value) > 80:  # 限制长度
            continue

        key = (fact_type, fact_value)
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "fact_type": fact_type,
            "fact_value": fact_value,
            "evidence_span": evidence_span,
        })

    # 展开主营业务
    expanded = []
    for item in out:
        if item["fact_type"] == "main_business":
            parts = split_main_business(item["fact_value"])
            if len(parts) > 1:
                for p in parts:
                    if p and len(p) <= 30:
                        expanded.append({
                            "fact_type": "main_business",
                            "fact_value": p,
                            "evidence_span": item["evidence_span"],
                        })
            else:
                expanded.append(item)
        else:
            expanded.append(item)

    # 最终去重
    final_out = []
    seen2 = set()
    for item in expanded:
        key = (item["fact_type"], item["fact_value"])
        if key in seen2:
            continue
        seen2.add(key)
        final_out.append(item)

    return final_out


def check_local_files(stock_dir: Path) -> Dict[str, Any]:
    """检查本地文件"""
    report = {
        "stock_dir_exists": stock_dir.exists(),
        "json_file_count": 0,
    }
    if not report["stock_dir_exists"]:
        raise FileNotFoundError(f"缺少目录: {stock_dir}")

    report["json_file_count"] = len(list(stock_dir.glob("*_detail.json")))
    logger.info("本地 stock_details 文件检查完成")
    logger.info(json.dumps(report, ensure_ascii=False, indent=2))

    if report["json_file_count"] == 0:
        raise RuntimeError("stock_dir 中没有 *_detail.json 文件")

    return report


def get_cache_path(cache_dir: Path, stock_id: str) -> Path:
    """获取缓存路径"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{stock_id}_facts.json"


def load_cache(cache_path: Path) -> Optional[List[Dict[str, str]]]:
    """加载缓存"""
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        facts = obj.get("facts", [])
        if isinstance(facts, list):
            return facts
    except Exception as e:
        logger.debug(f"缓存加载失败 {cache_path}: {e}")
        return None
    return None


def save_cache(cache_path: Path, facts: List[Dict[str, str]], raw_response: Optional[Dict[str, Any]] = None):
    """保存缓存"""
    payload = {
        "facts": facts,
        "raw_response": raw_response or {},
        "cached_at": datetime.now().isoformat(timespec="seconds"),
    }
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def get_processed_flag(processed_dir: Path, stock_id: str) -> Path:
    """获取处理标记路径"""
    processed_dir.mkdir(parents=True, exist_ok=True)
    return processed_dir / f"{stock_id}.done"


def ensure_parent_dir(path: Path):
    """确保父目录存在"""
    path.parent.mkdir(parents=True, exist_ok=True)


def save_failed_records(path: Path, records: List[Dict[str, Any]]):
    """保存失败记录"""
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


async def ensure_schema(conn):
    """确保表结构正确"""
    await conn.execute("""
        ALTER TABLE stock_facts
        ADD COLUMN IF NOT EXISTS source_id text
    """)
    await conn.execute("""
        ALTER TABLE stock_facts
        ADD COLUMN IF NOT EXISTS evidence_span text
    """)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_fact_unique
        ON stock_facts(stock_id, fact_type, fact_value)
    """)


async def stock_exists(conn, stock_id: str) -> bool:
    """检查股票是否存在"""
    cnt = await conn.fetchval("""
        SELECT COUNT(*) FROM stocks WHERE stock_id = $1
    """, stock_id)
    return int(cnt or 0) > 0


async def fetch_all_stock_ids(conn) -> Set[str]:
    """获取所有股票ID"""
    rows = await conn.fetch("SELECT stock_id FROM stocks")
    return {str(r["stock_id"]) for r in rows}


async def replace_stock_facts(conn, stock_id: str, facts: List[Dict[str, str]], source_id: str) -> int:
    """替换股票事实"""
    await conn.execute("""
        DELETE FROM stock_facts
        WHERE stock_id = $1
          AND source = 'jyhf_stock_detail'
    """, stock_id)

    count = 0
    for f in facts:
        try:
            await conn.execute("""
                INSERT INTO stock_facts (
                    stock_id, fact_type, fact_value, source, confidence,
                    source_id, evidence_span, created_at
                ) VALUES (
                    $1, $2, $3, 'jyhf_stock_detail', 1.0,
                    $4, $5, NOW()
                )
                ON CONFLICT (stock_id, fact_type, fact_value) DO UPDATE SET
                    source = EXCLUDED.source,
                    confidence = EXCLUDED.confidence,
                    source_id = EXCLUDED.source_id,
                    evidence_span = EXCLUDED.evidence_span
            """,
            stock_id,
            f["fact_type"],
            f["fact_value"],
            source_id,
            f["evidence_span"],
            )
            count += 1
        except Exception as e:
            logger.warning(f"插入失败 {stock_id} - {f.get('fact_type')}: {e}")
    return count


async def fetch_fact_stock_ids(conn) -> Set[str]:
    """获取已有事实的股票ID"""
    rows = await conn.fetch("""
        SELECT DISTINCT stock_id
        FROM stock_facts
        WHERE source = 'jyhf_stock_detail'
    """)
    return {str(r["stock_id"]) for r in rows}


def gather_stock_files(stock_dir: Path, stock: Optional[str] = None) -> List[Path]:
    """收集股票文件"""
    if stock:
        return [stock_dir / f"{stock}_detail.json"]
    return sorted(stock_dir.glob("*_detail.json"))


def extract_stock_id_from_file(fp: Path) -> str:
    """从文件名提取股票ID"""
    return fp.name.replace("_detail.json", "")


async def validate_all(conn, expected_stock_ids: Set[str]) -> Dict[str, Any]:
    """全量校验"""
    existing_fact_stock_ids = await fetch_fact_stock_ids(conn)
    missing = sorted(list(expected_stock_ids - existing_fact_stock_ids))
    return {
        "expected_stock_count": len(expected_stock_ids),
        "processed_fact_stock_count": len(expected_stock_ids & existing_fact_stock_ids),
        "missing_count": len(missing),
        "missing_stock_ids": missing[:100],
        "ok": len(missing) == 0,
    }


# =========================
# 主函数（完全保留您的代码）
# =========================

async def main():
    ap = argparse.ArgumentParser(description="批量提取股票事实并落库")
    ap.add_argument("--stock-dir", default="theme_data_complete/stock_details", help="股票详情 JSON 目录")
    ap.add_argument("--stock", type=str, help="仅处理一个股票，如 000021")
    ap.add_argument("--deepseek-api-key", default="", help="DeepSeek API Key")
    ap.add_argument("--cache-dir", default="tmp/stock_facts_cache", help="缓存目录")
    ap.add_argument("--processed-dir", default="tmp/stock_facts_processed", help="断点标记目录")
    ap.add_argument("--force-refresh", action="store_true", help="忽略缓存并重新抽取")
    ap.add_argument("--limit", type=int, default=0, help="限制处理数量，便于测试")
    ap.add_argument("--failed-out", default="tmp/stock_facts_failed/failed_stock_ids.json", help="失败股票输出文件")
    ap.add_argument("--retry-failed-file", default="", help="只重跑失败清单中的股票")
    ap.add_argument("--fail-fast", action="store_true", help="遇到单股票失败时立即中断")
    ap.add_argument("--verbose", action="store_true", help="输出详细日志")
    args = ap.parse_args()

    # 设置日志级别
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # 检查股票目录
    stock_dir = Path(args.stock_dir)
    cache_dir = Path(args.cache_dir)
    processed_dir = Path(args.processed_dir)

    check_local_files(stock_dir)

    # 获取API Key
    api_key = args.deepseek_api_key.strip() or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("请提供 DeepSeek API Key (通过 --deepseek-api-key 或 DEEPSEEK_API_KEY 环境变量)")

    ds = DeepSeekClient(api_key=api_key)

    # 收集要处理的文件
    if args.retry_failed_file:
        retry_path = Path(args.retry_failed_file)
        if retry_path.exists():
            retry_records = read_json(retry_path)
            retry_stock_ids = []

            if isinstance(retry_records, list):
                for x in retry_records:
                    if isinstance(x, dict) and x.get("stock_id"):
                        retry_stock_ids.append(str(x["stock_id"]))
                    elif isinstance(x, str):
                        retry_stock_ids.append(x)

            files = [stock_dir / f"{sid}_detail.json" for sid in retry_stock_ids if sid]
            logger.info(f"从失败清单加载 {len(files)} 个股票")
        else:
            logger.warning(f"失败文件不存在: {retry_path}")
            files = []
    else:
        files = gather_stock_files(stock_dir, args.stock)

    if args.limit and args.limit > 0:
        files = files[:args.limit]

    if not files:
        logger.warning("没有文件需要处理")
        return

    # 连接数据库 - 使用正确的异步上下文管理器
    manager = get_postgres_config()
    await manager.connect()
    logger.info("数据库连接成功")

    try:
        # 获取一个连接
        conn = await manager.acquire()  # 现在这行可以正常工作了
        try:
            await ensure_schema(conn)

            # 获取数据库中所有股票ID
            all_stock_ids_in_db = await fetch_all_stock_ids(conn)

            # 过滤出在数据库中存在的股票
            eligible_files = []
            skipped_no_stock_master_before = 0
            for fp in files:
                sid = extract_stock_id_from_file(fp)
                if sid not in all_stock_ids_in_db:
                    skipped_no_stock_master_before += 1
                    logger.debug(f"跳过 {sid}: 不在stocks表中")
                    continue
                eligible_files.append(fp)

            expected_stock_ids = {extract_stock_id_from_file(fp) for fp in eligible_files}

            pre_stats = {
                "requested_files": len(files),
                "eligible_files": len(eligible_files),
                "skipped_no_stock_master_before": skipped_no_stock_master_before,
                "force_refresh": args.force_refresh,
                "cache_dir": str(cache_dir),
                "processed_dir": str(processed_dir),
                "failed_out": str(args.failed_out),
            }
            logger.info("==== 处理前统计 ====")
            logger.info(json.dumps(pre_stats, ensure_ascii=False, indent=2))

            stats = {
                "processed_files": 0,
                "facts_upserted": 0,
                "used_cache": 0,
                "llm_called": 0,
                "skipped_bad_file": 0,
                "skipped_already_processed": 0,
                "llm_failed": 0,
            }

            failed_records = []

            pbar = tqdm(eligible_files, desc="提取 stock_facts", unit="stock")

            for fp in pbar:
                stock_id = extract_stock_id_from_file(fp)
                done_flag = get_processed_flag(processed_dir, stock_id)

                # 检查是否已处理
                if done_flag.exists() and not args.force_refresh:
                    stats["skipped_already_processed"] += 1
                    pbar.set_postfix({
                        "done": stats["processed_files"],
                        "cache": stats["used_cache"],
                        "llm": stats["llm_called"],
                        "skip": stats["skipped_already_processed"],
                        "fail": stats["llm_failed"],
                    })
                    continue

                # 读取文件
                raw = read_json(fp)
                data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw
                
                if not isinstance(data, dict):
                    stats["skipped_bad_file"] += 1
                    failed_records.append({
                        "stock_id": stock_id,
                        "file": str(fp),
                        "error": "bad_json_or_missing_data",
                    })
                    pbar.set_postfix({
                        "done": stats["processed_files"],
                        "cache": stats["used_cache"],
                        "llm": stats["llm_called"],
                        "skip": stats["skipped_already_processed"],
                        "fail": stats["llm_failed"],
                    })
                    if args.fail_fast:
                        raise RuntimeError(f"坏文件: {fp}")
                    continue

                # 获取实际股票ID
                real_stock_id = str(data.get("stockId") or "").strip()
                if not real_stock_id:
                    stats["skipped_bad_file"] += 1
                    failed_records.append({
                        "stock_id": stock_id,
                        "file": str(fp),
                        "error": "missing_stockId",
                    })
                    pbar.set_postfix({
                        "done": stats["processed_files"],
                        "cache": stats["used_cache"],
                        "llm": stats["llm_called"],
                        "skip": stats["skipped_already_processed"],
                        "fail": stats["llm_failed"],
                    })
                    if args.fail_fast:
                        raise RuntimeError(f"缺少 stockId: {fp}")
                    continue

                if real_stock_id != stock_id:
                    stock_id = real_stock_id

                # 检查缓存
                cache_path = get_cache_path(cache_dir, stock_id)
                facts = None
                raw_resp = None

                if not args.force_refresh:
                    facts = load_cache(cache_path)
                    if facts is not None:
                        stats["used_cache"] += 1
                        logger.debug(f"使用缓存: {stock_id}")

                # 调用LLM
                if facts is None:
                    prompt = build_stock_fact_prompt(data)
                    messages = [
                        {"role": "system", "content": STOCK_FACT_EXTRACT_SYSTEM},
                        {"role": "user", "content": prompt},
                    ]

                    try:
                        logger.debug(f"调用LLM: {stock_id}")
                        raw_resp = ds.run_json_object(messages, max_tokens=3000, temperature=0.1)  # 增加到3000
                        facts = normalize_llm_facts(raw_resp)
                        save_cache(cache_path, facts, raw_resp)
                        stats["llm_called"] += 1
                        logger.debug(f"LLM成功: {stock_id}, 获取 {len(facts)} 条事实")
                    except Exception as e:
                        logger.warning(f"LLM 抽取失败 stock={stock_id}: {e}")
                        stats["llm_failed"] += 1
                        failed_records.append({
                            "stock_id": stock_id,
                            "file": str(fp),
                            "error": repr(e),
                        })
                        pbar.set_postfix({
                            "done": stats["processed_files"],
                            "cache": stats["used_cache"],
                            "llm": stats["llm_called"],
                            "skip": stats["skipped_already_processed"],
                            "fail": stats["llm_failed"],
                        })
                        if args.fail_fast:
                            raise
                        continue

                # 写入数据库
                cnt = await replace_stock_facts(
                    conn=conn,
                    stock_id=stock_id,
                    facts=facts or [],
                    source_id=f"{stock_id}_detail",
                )

                # 标记完成
                done_flag.touch()
                stats["facts_upserted"] += cnt
                stats["processed_files"] += 1

                pbar.set_postfix({
                    "done": stats["processed_files"],
                    "cache": stats["used_cache"],
                    "llm": stats["llm_called"],
                    "skip": stats["skipped_already_processed"],
                    "fail": stats["llm_failed"],
                })

            pbar.close()

            # 保存失败记录
            failed_out = Path(args.failed_out)
            save_failed_records(failed_out, failed_records)
            logger.info(f"失败股票清单已输出到: {failed_out}")

            # 输出统计
            logger.info("==== 落库统计 ====")
            logger.info(json.dumps(stats, ensure_ascii=False, indent=2))

            # 全量校验
            validation = await validate_all(conn, expected_stock_ids)
            logger.info("==== 全量校验 ====")
            logger.info(json.dumps(validation, ensure_ascii=False, indent=2))

            if not validation["ok"]:
                logger.warning(f"stock_facts 全量校验失败，缺少 {validation['missing_count']} 个股票")
                logger.warning(f"失败清单见 {args.failed_out}")
                # 不抛出异常，只是警告
            else:
                logger.info("stock_facts 批量处理完成，且全量校验通过。")

        finally:
            # 释放连接
            await manager.release(conn)

    finally:
        await manager.disconnect()
        logger.info("数据库连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())