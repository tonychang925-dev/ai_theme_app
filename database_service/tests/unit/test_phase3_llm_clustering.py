"""Phase3 LLM事件聚类测试 - 最终正确版本"""

from __future__ import annotations

import json
import os
import time
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple
from collections import Counter, defaultdict

import pytest
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


REPO_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
EVENTS_FILE = REPO_ROOT / "evaluate_service/data/raw/ai_processed_events.json"
OUT_REPORT_FILE = REPO_ROOT / "tmp/phase3_clustering_final_report.json"

# 1.5B模型路径
MODEL_PATH = REPO_ROOT / "model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf"
TEST_SIZE = 30
BATCH_SIZE = 5

if not MODEL_PATH.exists():
    print(f"⚠️ 1.5B模型不存在，回退到0.5B模型")
    MODEL_PATH = REPO_ROOT / ".qwen_cache/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775"


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_events():
    """从ai_processed_events.json加载事件"""
    data = _load_json(EVENTS_FILE)
    events_data = data if isinstance(data, list) else data.get("events", [])
    
    events = []
    for item in events_data:
        content = item.get("content", "")
        
        events.append({
            "event_id": item["event_id"],
            "title": item["title"],
            "content": content,
            "true_theme": item["title"]
        })
    
    print(f"\n📊 从文件加载了 {len(events)} 个事件")
    return events


class IncrementalCluster:
    def __init__(self, model_path: Path):
        self.model_path = str(model_path)
        self.is_gguf = str(model_path).endswith('.gguf')
        
        print(f"\n📦 加载模型: {model_path}")
        print(f"📦 模型格式: {'GGUF (1.5B)' if self.is_gguf else 'Transformers (0.5B)'}")
        print(f"📦 批处理大小: {BATCH_SIZE}")
        start_time = time.time()
        
        if self.is_gguf:
            try:
                from llama_cpp import Llama
                self.llm = Llama(
                    model_path=str(model_path),
                    n_ctx=2048,
                    n_threads=8,
                    n_gpu_layers=-1 if torch.cuda.is_available() else 0,
                    verbose=False,
                    temperature=0.0,
                )
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
                self.model = None
                self.tokenizer = None
            except ImportError:
                print("❌ 请安装llama-cpp-python: pip install llama-cpp-python")
                raise
        else:
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(model_path), 
                trust_remote_code=True,
                use_fast=True
            )
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            model_kwargs = {"trust_remote_code": True}
            
            if torch.cuda.is_available():
                model_kwargs["torch_dtype"] = torch.float16
                self.device = torch.device("cuda")
            else:
                model_kwargs["torch_dtype"] = torch.float32
                self.device = torch.device("cpu")
            
            self.model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                **model_kwargs
            )
            self.model.to(self.device)
            self.model.eval()
            self.llm = None
        
        load_time = time.time() - start_time
        print(f"✅ 模型加载完成，耗时: {load_time:.2f}秒，设备: {self.device}")
        
        self.total_calls = 0
        self.total_time = 0

    def _generate_text(self, prompt: str, max_new_tokens: int = 20) -> str:
        """生成文本"""
        if self.is_gguf and self.llm is not None:
            response = self.llm(
                prompt,
                max_tokens=max_new_tokens,
                stop=["\n"],
                echo=False,
                temperature=0.0,
            )
            return response["choices"][0]["text"].strip()
        else:
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=self.tokenizer.pad_token_id,
                )
            gen_ids = outputs[0][inputs["input_ids"].shape[1]:]
            return self.tokenizer.decode(gen_ids, skip_special_tokens=True).strip()

    def batch_match(self, new_event: Dict, clusters: List[Dict], start_idx: int) -> List[Tuple[int, float]]:
        """批量匹配 - 只返回明确匹配的题材"""
        if not clusters:
            return []
        
        batch_clusters = clusters[start_idx:start_idx + BATCH_SIZE]
        if not batch_clusters:
            return []
        
        # 构建批量比较的prompt
        comparisons = []
        for i, cluster in enumerate(batch_clusters):
            rep = cluster["events"][0]
            comparisons.append(
                f"{start_idx + i + 1}. {rep['content'][:100]}"
            )
        
        prompt = f"""新事件：{new_event['content'][:100]}

请判断新事件与以下哪些题材属于同一类：

{chr(10).join(comparisons)}

只输出匹配的题材编号，用逗号分隔。如果没有匹配的，输出"无"。
例如：1,3,5

答案："""
        
        start = time.time()
        output = self._generate_text(prompt, max_new_tokens=20)
        elapsed = time.time() - start
        
        self.total_calls += 1
        self.total_time += elapsed
        
        # 解析结果
        results = []
        if output.strip() and output.strip() != "无":
            parts = output.replace('，', ',').split(',')
            for part in parts:
                try:
                    idx = int(part.strip()) - 1
                    if 0 <= idx < len(batch_clusters):
                        results.append((start_idx + idx, 1.0))
                except:
                    continue
        
        return results

    def incremental_cluster(self, events: List[Dict]) -> Dict:
        """增量聚类 - 最终正确版本"""
        clusters = []
        
        print("\n🔄 开始增量聚类...")
        print("-" * 70)
        
        for i, event in enumerate(events, 1):
            print(f"\n📌 处理事件 {i}/{len(events)}: {event['title'][:30]}...")
            
            if not clusters:
                clusters.append({
                    "theme_name": f"题材_{len(clusters)+1}",
                    "events": [event],
                    "true_themes": [event["true_theme"]]
                })
                print(f"   ➕ 创建新题材 题材_1")
                continue
            
            # 获取所有匹配的题材
            all_matches = []
            for start in range(0, len(clusters), BATCH_SIZE):
                matches = self.batch_match(event, clusters, start)
                all_matches.extend(matches)
            
            if len(all_matches) == 1:
                # 唯一匹配
                idx = all_matches[0][0]
                clusters[idx]["events"].append(event)
                clusters[idx]["true_themes"].append(event["true_theme"])
                print(f"   ✅ 加入 {clusters[idx]['theme_name']}")
            elif len(all_matches) > 1:
                # 多个匹配 - 说明模型混乱，创建新题材
                new_name = f"题材_{len(clusters)+1}"
                clusters.append({
                    "theme_name": new_name,
                    "events": [event],
                    "true_themes": [event["true_theme"]]
                })
                print(f"   ⚠️ 多个匹配 ({len(all_matches)}个)，创建 {new_name}")
            else:
                # 无匹配
                new_name = f"题材_{len(clusters)+1}"
                clusters.append({
                    "theme_name": new_name,
                    "events": [event],
                    "true_themes": [event["true_theme"]]
                })
                print(f"   ➕ 创建新题材 {new_name}")
        
        return {
            "clusters": clusters,
            "stats": {
                "total_events": len(events),
                "total_clusters": len(clusters),
                "total_calls": self.total_calls,
                "total_time": self.total_time,
                "avg_time_per_call": self.total_time / self.total_calls if self.total_calls > 0 else 0
            }
        }


def evaluate_clusters(clusters: List[Dict]) -> Dict:
    """评估聚类质量"""
    total_events = sum(len(c["events"]) for c in clusters)
    total_correct = 0
    cluster_details = []
    
    print("\n" + "="*70)
    print("📊 聚类结果分析")
    print("="*70)
    
    for cluster in clusters:
        theme_counter = Counter(cluster["true_themes"])
        dominant_theme, dominant_count = theme_counter.most_common(1)[0]
        purity = dominant_count / len(cluster["events"])
        
        total_correct += dominant_count
        
        errors = []
        for event in cluster["events"]:
            if event["true_theme"] != dominant_theme:
                errors.append({
                    "event_id": event["event_id"],
                    "title": event["title"],
                    "true_theme": event["true_theme"]
                })
        
        cluster_details.append({
            "theme_name": cluster["theme_name"],
            "size": len(cluster["events"]),
            "dominant_theme": dominant_theme,
            "dominant_count": dominant_count,
            "purity": purity,
            "theme_distribution": dict(theme_counter),
            "errors": errors
        })
        
        print(f"\n📍 {cluster['theme_name']} (共{len(cluster['events'])}个事件, 纯度{purity:.2%}):")
        print(f"   主导题材: {dominant_theme}")
        if errors:
            print(f"   错误归类: {len(errors)}个")
    
    avg_purity = sum(d["purity"] for d in cluster_details) / len(cluster_details)
    overall_purity = total_correct / total_events
    
    return {
        "total_clusters": len(clusters),
        "avg_purity": avg_purity,
        "overall_purity": overall_purity,
        "correctly_clustered": total_correct,
        "total_events": total_events,
        "cluster_details": cluster_details
    }


@pytest.mark.asyncio
async def test_clustering_final():
    """测试聚类效果 - 最终版"""
    print("\n" + "="*80)
    print("🧪 测试聚类效果（最终版）")
    print("="*80)
    
    # 1. 加载事件
    all_events = _load_events()
    
    # 2. 采样30个
    sampled_events = random.sample(all_events, min(TEST_SIZE, len(all_events)))
    
    print(f"\n📊 测试集: {len(sampled_events)}个事件")
    theme_counter = Counter([e["true_theme"] for e in sampled_events])
    for theme, count in theme_counter.most_common():
        print(f"  {theme}: {count}个")
    
    # 3. 初始化聚类器
    clusterer = IncrementalCluster(MODEL_PATH)
    
    # 4. 执行聚类
    print("\n" + "-"*70)
    start_time = time.time()
    result = clusterer.incremental_cluster(sampled_events)
    total_time = time.time() - start_time
    
    # 5. 评估
    evaluation = evaluate_clusters(result["clusters"])
    
    print("\n" + "="*80)
    print("📊 最终评估结果")
    print("="*80)
    print(f"\n⏱️  总耗时: {total_time:.1f}s")
    print(f"🔄 LLM调用: {result['stats']['total_calls']}次")
    print(f"⚡ 平均每次: {result['stats']['avg_time_per_call']:.2f}s")
    print(f"\n📊 聚类统计:")
    print(f"   - 总事件数: {evaluation['total_events']}")
    print(f"   - 聚类数量: {evaluation['total_clusters']}个")
    print(f"\n🎯 纯度指标:")
    print(f"   - 平均聚类纯度: {evaluation['avg_purity']:.2%}")
    print(f"   - 整体聚类纯度: {evaluation['overall_purity']:.2%}")
    print(f"   - 正确聚类: {evaluation['correctly_clustered']}/{evaluation['total_events']}")
    
    # 6. 保存报告
    report = {
        "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_config": {
            "sample_size": len(sampled_events),
            "model_path": str(MODEL_PATH),
            "model_size": "1.5B" if str(MODEL_PATH).endswith('.gguf') else "0.5B",
            "batch_size": BATCH_SIZE
        },
        "clustering_result": [
            {
                "theme_name": c["theme_name"],
                "size": len(c["events"]),
                "purity": next(d["purity"] for d in evaluation["cluster_details"] if d["theme_name"] == c["theme_name"]),
                "dominant_theme": next(d["dominant_theme"] for d in evaluation["cluster_details"] if d["theme_name"] == c["theme_name"]),
                "events": [
                    {
                        "index": sampled_events.index(e) + 1,
                        "event_id": e["event_id"],
                        "title": e["title"],
                        "true_theme": e["true_theme"]
                    } for e in c["events"]
                ]
            } for c in result["clusters"]
        ],
        "evaluation": evaluation,
        "performance": result["stats"]
    }
    
    OUT_REPORT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    print(f"\n💾 详细报告已保存: {OUT_REPORT_FILE}")