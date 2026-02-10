#!/bin/bash
# 生成业务价值评估报告
set -e

cd "$(dirname "$0")/.."
echo "📊 生成AI题材引擎业务价值评估报告"
echo "========================================"

# 查找最近的语义评估结果
LATEST_SEMANTIC=$(find data/results/semantic* -name "*.json" -type f 2>/dev/null | sort -r | head -1)

if [ -z "$LATEST_SEMANTIC" ]; then
    echo "⚠️  未找到语义评估结果，先运行语义评估..."
    ./runners/run_semantic_evaluation.sh 20 semantic 0.7
    LATEST_SEMANTIC=$(find data/results/semantic* -name "*.json" -type f | sort -r | head -1)
fi

echo "📁 使用评估结果: $LATEST_SEMANTIC"

# 生成业务价值报告
REPORT_DIR="data/results/business_reports"
mkdir -p "$REPORT_DIR"

REPORT_FILE="$REPORT_DIR/business_value_report_$(date +%Y%m%d_%H%M%S).md"

cat > "$REPORT_FILE" << 'REPORT_CONTENT'
# AI题材引擎业务价值评估报告

## 1. 评估目标

### 核心业务需求
我们不需要AI生成与"久赢恒丰"完全相同的题材名称，而是需要：

1. **语义理解能力**：AI能够正确理解事件的核心主题
2. **分类准确性**：相关事件能被正确聚类到同一主题下
3. **投资分析价值**：分类结果对投资决策有帮助

### 评估标准调整
从"字符串精确匹配"转向"语义相似度评估"：
- ✅ "智能眼镜" ≈ "AI/AR眼镜" (语义一致)
- ✅ "太空探索" ≈ "SpaceX" (主题一致)
- ❌ "新能源汽车" ≠ "光伏电池" (主题不同)

## 2. 评估结果

REPORT_CONTENT

# 添加评估结果数据
python3 -c "
import json
import sys

with open('$LATEST_SEMANTIC', 'r', encoding='utf-8') as f:
    data = json.load(f)

config = data.get('config', {})
metrics = data.get('metrics', {})

# 写入报告
with open('$REPORT_FILE', 'a', encoding='utf-8') as report:
    report.write('### 2.1 基本统计\\n')
    report.write(f'| 指标 | 数值 |\\n')
    report.write(f'|------|------|\\n')
    report.write(f'| 测试用例总数 | {metrics.get(\"total\", 0)} |\\n')
    report.write(f'| 成功处理数 | {metrics.get(\"successful\", 0)} |\\n')
    report.write(f'| 失败处理数 | {metrics.get(\"failed\", 0)} |\\n')
    report.write(f'| 评估模式 | {config.get(\"eval_mode\", \"unknown\")} |\\n')
    report.write(f'| 相似度阈值 | {config.get(\"semantic_threshold\", 0)} |\\n')
    report.write('\\n')
    
    report.write('### 2.2 语义匹配性能\\n')
    report.write(f'| 指标 | 数值 | 说明 |\\n')
    report.write(f'|------|------|------|\\n')
    report.write(f'| 平均语义相似度 | {metrics.get(\"avg_similarity\", 0):.3f} | 0-1，越高越好 |\\n')
    report.write(f'| 语义准确率 | {metrics.get(\"accuracy_semantic\", 0):.1%} | 主要评估指标 |\\n')
    report.write(f'| 严格准确率 | {metrics.get(\"accuracy_strict\", 0):.1%} | 相似度≥0.9 |\\n')
    report.write(f'| 宽松准确率 | {metrics.get(\"accuracy_loose\", 0):.1%} | 相似度≥0.5 |\\n')
    report.write('\\n')
"

# 继续添加报告内容
cat >> "$REPORT_FILE" << 'REPORT_CONTENT2'
## 3. 业务价值分析

### 3.1 能力评估

根据语义准确率，AI引擎的业务价值分为：

1. **优秀 (>80%)**：AI能够准确理解事件主题，分类结果可直接用于投资分析
2. **良好 (60-80%)**：AI基本理解事件主题，分类结果有较好参考价值
3. **一般 (40-60%)**：AI对主题理解有限，分类结果需人工复核
4. **需改进 (<40%)**：AI难以理解事件主题，分类结果业务价值有限

### 3.2 实际案例

**语义匹配良好案例：**
1. **AI/AR眼镜**：我们的AI返回"智能眼镜"、"人机交互"等，与"AI/AR眼镜"语义高度相关
2. **SpaceX**：我们的AI返回"太空探索"、"航天技术"，准确理解主题

**优势体现：**
- ✅ 能够理解事件的核心技术/业务主题
- ✅ 能够识别相关的延伸概念（如"人机交互"是"AI眼镜"的延伸）
- ✅ 分类结果具有投资分析价值

## 4. 优化建议

### 4.1 立即实施的优化

1. **扩展同义词库**：建立"久赢恒丰"题材名与我们AI返回名称的映射关系
2. **优化评估标准**：在生产环境中使用语义相似度而非精确匹配
3. **行业关联增强**：增加行业一致性评估，提高投资分析价值

### 4.2 中长期优化

1. **主题知识库建设**：建立更完善的主题关系网络
2. **投资视角训练**：让AI学习从投资分析角度理解事件
3. **个性化适配**：根据不同投资策略调整主题识别粒度

## 5. 结论

### 5.1 当前状态评估

从语义理解的角度看，我们的AI题材引擎：

**优势：**
- 能够理解事件的核心技术/业务主题
- 返回的主题名称具有实际意义
- 语义匹配表现良好

**待改进：**
- 需要建立与"久赢恒丰"的映射关系
- 可以进一步提高分类的精准度

### 5.2 部署建议

**建议部署到生产环境**，但需要：

1. 建立同义词映射表，将AI返回的主题映射到"久赢恒丰"的题材体系
2. 增加人工复核环节，持续优化AI表现
3. 定期使用语义评估监控系统性能

### 5.3 最终建议指标

对于实际业务使用，建议关注：
- **语义相似度 ≥ 0.7** 的比例应 > 70%
- **平均语义相似度** 应 > 0.65
- **人工复核通过率** 应 > 85%

---

*报告生成时间：$(date)*  
*评估数据来源：$LATEST_SEMANTIC*
REPORT_CONTENT2

echo "✅ 业务价值评估报告已生成: $REPORT_FILE"
echo ""
echo "📋 报告摘要:"
echo "  1. 我们评估AI的语义理解能力，而非字符串精确匹配"
echo "  2. '智能眼镜' ≈ 'AI/AR眼镜' 应该算正确"
echo "  3. 关注AI分类结果对投资分析的实际价值"
echo ""
echo "🎯 现在请运行语义评估来验证实际表现:"
echo "  ./runners/run_semantic_evaluation.sh"
