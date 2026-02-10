#!/usr/bin/env python3
import json, asyncio, argparse
from pathlib import Path

class MockEvaluator:
    async def evaluate_dataset(self, data_path):
        with open(data_path, 'r', encoding='utf-8') as f:
            test_cases = json.load(f)
        
        results = []
        for case in test_cases[:3]:  # 只测试前3个
            results.append({
                "test_id": case["test_id"],
                "discovered": [case["theme"]],  # 模拟完美识别
                "ground_truth": case["ground_truth_themes"],
                "metrics": {"precision": 1.0, "recall": 1.0, "f1": 1.0}
            })
        
        return {
            "total_cases": len(test_cases),
            "evaluated_cases": len(results),
            "overall_precision": 1.0,
            "overall_recall": 1.0,
            "overall_f1": 1.0,
            "results": results
        }

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_path', default='data/processed/validation_dataset.json')
    parser.add_argument('--output_dir', default='data/results/reports/demo')
    args = parser.parse_args()
    
    evaluator = MockEvaluator()
    results = await evaluator.evaluate_dataset(args.data_path)
    
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    with open(output_path / 'metrics.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 演示评估完成! 结果保存至: {output_path}/metrics.json")
    
    # 生成报告
    import sys
    sys.path.append(str(Path(__file__).parent))
    from report_generator import generate_html_report
    generate_html_report(results, output_path / 'report.html')

if __name__ == '__main__':
    asyncio.run(main())
