import subprocess
import time
from typing import List, Dict

LLAMA_BIN = "llama-cli"
MODEL_PATH = "model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf"

def judge_event_themes(
    event: str,
    themes: List[str],
    timeout: int = 120
) -> Dict[str, bool]:
    theme_lines = "\n".join(
        [f"{i+1}. {t}" for i, t in enumerate(themes)]
    )

    prompt = f"""
你是一个严格的金融题材裁判。

给定一个【事件】和【多个候选题材】，
请判断该事件是否“属于”每一个题材。

判断标准：
- 是否处于同一产业链 / 技术体系
- 是否存在直接业务或技术关联
- 仅凭“都是高科技”不能算

输出要求：
- 每一行一个题材
- 格式固定：题材名=是 或 题材名=否
- 不要任何解释

事件：
{event}

候选题材：
{theme_lines}
""".strip()

    cmd = [
        LLAMA_BIN,
        "-m", MODEL_PATH,
        "--ctx-size", "1024",
        "-t", "8",
        "--temp", "0",
        "--top-p", "0.1",
        "--repeat-penalty", "1.2",
        "--n-predict", "128",
        "-p", prompt
    ]

    start = time.time()

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout
    )

    duration = time.time() - start

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    output = result.stdout.strip()
    lines = output.splitlines()

    parsed = {}
    for line in lines:
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        parsed[k.strip()] = v.strip() == "是"

    print(f"\n⏱ 用时: {duration:.2f}s")
    return parsed


if __name__ == "__main__":
    event_text = "我国科研团队在可控核聚变装置中实现等离子体稳定运行新突破"

    candidate_themes = [
        "核聚变技术",
        "半导体光刻胶",
        "商业航天",
        "新能源",
        "高端装备制造",
        "军工",
        "AI算力",
        "新材料",
        "半导体设备",
        "先进制造"
    ]

    results = judge_event_themes(event_text, candidate_themes)

    print("\n🧠 裁判结果")
    print("-" * 40)
    for theme, ok in results.items():
        print(f"{theme:12s} : {'✅ 是' if ok else '❌ 否'}")
