# evaluate_service/scripts/verify_data_integrity.py
"""
验证数据完整性脚本
检查重新生成的事件数据是否包含完整上下文信息
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
import sys

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataIntegrityVerifier:
    """数据完整性验证器"""
    
    def __init__(self):
        self.verification_results = {
            'total_events': 0,
            'passed_checks': 0,
            'failed_checks': 0,
            'check_details': []
        }
    
    def verify_event_data(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证单个事件数据的完整性
        
        Args:
            event_data: 事件数据
            
        Returns:
            验证结果
        """
        checks = []
        
        # 检查1: 必要字段
        required_fields = [
            'news_id', 'event_type', 'impact_industries', 'direction',
            'confidence', 'summary', 'theme_directive', 'original_data'
        ]
        
        missing_fields = []
        for field in required_fields:
            if field not in event_data:
                missing_fields.append(field)
        
        has_required_fields = len(missing_fields) == 0
        checks.append({
            'check': 'required_fields',
            'passed': has_required_fields,
            'details': f"缺失字段: {missing_fields}" if missing_fields else "所有必要字段完整"
        })
        
        # 检查2: 原始数据保存
        original_data = event_data.get('original_data', {})
        has_original_content = bool(original_data.get('content'))
        checks.append({
            'check': 'original_content_saved',
            'passed': has_original_content,
            'details': f"原始内容长度: {len(original_data.get('content', ''))}"
        })
        
        # 检查3: 主题指令
        theme_directive = event_data.get('theme_directive', {})
        has_valid_theme_directive = (
            'action' in theme_directive and 
            'confidence' in theme_directive
        )
        checks.append({
            'check': 'valid_theme_directive',
            'passed': has_valid_theme_directive,
            'details': f"指令: {theme_directive.get('action', 'none')}, 置信度: {theme_directive.get('confidence', 0)}"
        })
        
        # 检查4: AI摘要质量
        ai_summary = event_data.get('summary', '')
        has_meaningful_summary = len(ai_summary) >= 50  # 至少50字符
        checks.append({
            'check': 'meaningful_ai_summary',
            'passed': has_meaningful_summary,
            'details': f"摘要长度: {len(ai_summary)} 字符"
        })
        
        # 检查5: 行业信息
        industries = event_data.get('impact_industries', [])
        has_industries = len(industries) > 0
        checks.append({
            'check': 'has_impact_industries',
            'passed': has_industries,
            'details': f"影响行业: {industries}"
        })
        
        # 检查6: AI响应完整
        ai_response = event_data.get('ai_response', {})
        has_ai_response = bool(ai_response) and isinstance(ai_response, dict)
        checks.append({
            'check': 'has_complete_ai_response',
            'passed': has_ai_response,
            'details': f"AI响应字段: {list(ai_response.keys()) if ai_response else '无'}"
        })
        
        # 计算总通过率
        passed_checks = sum(1 for check in checks if check['passed'])
        total_checks = len(checks)
        
        return {
            'news_id': event_data.get('news_id', 'unknown'),
            'checks': checks,
            'passed_checks': passed_checks,
            'total_checks': total_checks,
            'pass_rate': passed_checks / total_checks if total_checks > 0 else 0,
            'overall_passed': passed_checks == total_checks
        }
    
    def verify_dataset(self, dataset_path: Path) -> Dict[str, Any]:
        """
        验证整个数据集
        
        Args:
            dataset_path: 数据集路径
            
        Returns:
            验证结果
        """
        logger.info(f"开始验证数据集: {dataset_path}")
        
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取事件列表
            if isinstance(data, dict) and 'events' in data:
                events = data['events']
                metadata = data.get('metadata', {})
            elif isinstance(data, list):
                events = data
                metadata = {}
            else:
                logger.error(f"未知的数据格式")
                return {}
            
            logger.info(f"找到 {len(events)} 个事件")
            
            all_results = []
            for event in events:
                result = self.verify_event_data(event)
                all_results.append(result)
                
                # 更新统计
                self.verification_results['total_events'] += 1
                if result['overall_passed']:
                    self.verification_results['passed_checks'] += 1
                else:
                    self.verification_results['failed_checks'] += 1
                
                self.verification_results['check_details'].append(result)
            
            # 计算总体统计
            total_pass_rate = (
                self.verification_results['passed_checks'] / 
                max(self.verification_results['total_events'], 1)
            )
            
            # 生成详细报告
            report = self._generate_detailed_report(all_results, metadata)
            
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ 验证完成!")
            logger.info(f"   总事件数: {self.verification_results['total_events']}")
            logger.info(f"   完全通过: {self.verification_results['passed_checks']} ({total_pass_rate:.1%})")
            logger.info(f"   部分失败: {self.verification_results['failed_checks']}")
            logger.info(f"{'='*60}")
            
            return report
            
        except Exception as e:
            logger.error(f"验证失败: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _generate_detailed_report(self, all_results: List[Dict], metadata: Dict) -> Dict[str, Any]:
        """生成详细报告"""
        # 按检查项统计
        check_stats = {}
        for result in all_results:
            for check in result['checks']:
                check_name = check['check']
                if check_name not in check_stats:
                    check_stats[check_name] = {'passed': 0, 'total': 0}
                check_stats[check_name]['total'] += 1
                if check['passed']:
                    check_stats[check_name]['passed'] += 1
        
        # 计算通过率
        for check_name, stats in check_stats.items():
            stats['pass_rate'] = stats['passed'] / max(stats['total'], 1)
        
        # 失败详情
        failed_events = []
        for result in all_results:
            if not result['overall_passed']:
                failed_checks = [c['check'] for c in result['checks'] if not c['passed']]
                failed_events.append({
                    'news_id': result['news_id'],
                    'failed_checks': failed_checks,
                    'pass_rate': result['pass_rate']
                })
        
        report = {
            'summary': {
                'total_events': self.verification_results['total_events'],
                'passed_events': self.verification_results['passed_checks'],
                'failed_events': self.verification_results['failed_checks'],
                'overall_pass_rate': self.verification_results['passed_checks'] / max(self.verification_results['total_events'], 1),
                'verification_time': datetime.now().isoformat()
            },
            'metadata': metadata,
            'check_statistics': check_stats,
            'failed_events_detail': failed_events[:10],  # 只保留前10个失败详情
            'sample_passed_events': [
                {
                    'news_id': r['news_id'],
                    'pass_rate': r['pass_rate']
                } for r in all_results if r['overall_passed']
            ][:5]  # 只保留5个成功样例
        }
        
        return report
    
    def save_report(self, report: Dict[str, Any], output_path: Path):
        """保存验证报告"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"验证报告已保存到: {output_path}")


def compare_datasets(old_path: Path, new_path: Path):
    """比较新旧数据集"""
    logger.info(f"\n{'='*60}")
    logger.info("📊 数据集对比分析")
    logger.info(f"{'='*60}")
    
    try:
        with open(old_path, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
        
        with open(new_path, 'r', encoding='utf-8') as f:
            new_data = json.load(f)
        
        # 提取事件
        old_events = old_data['events'] if isinstance(old_data, dict) and 'events' in old_data else old_data
        new_events = new_data['events'] if isinstance(new_data, dict) and 'events' in new_data else new_data
        
        logger.info(f"旧数据集事件数: {len(old_events)}")
        logger.info(f"新数据集事件数: {len(new_events)}")
        
        # 检查字段完整性对比
        def get_field_stats(events):
            field_counts = {}
            for event in events:
                for field in event.keys():
                    field_counts[field] = field_counts.get(field, 0) + 1
            return field_counts
        
        old_fields = get_field_stats(old_events[:10])  # 只检查前10个
        new_fields = get_field_stats(new_events[:10])
        
        logger.info("\n字段对比:")
        logger.info("旧数据集字段: " + ", ".join(sorted(old_fields.keys())))
        logger.info("新数据集字段: " + ", ".join(sorted(new_fields.keys())))
        
        # 检查新增字段
        new_field_set = set(new_fields.keys())
        old_field_set = set(old_fields.keys())
        added_fields = new_field_set - old_field_set
        removed_fields = old_field_set - new_field_set
        
        if added_fields:
            logger.info(f"✅ 新增字段: {added_fields}")
        if removed_fields:
            logger.info(f"⚠️  移除字段: {removed_fields}")
        
        # 检查原始数据保存情况
        has_original_count = sum(1 for e in new_events[:20] if 'original_data' in e and e['original_data'].get('content'))
        logger.info(f"新数据集中有原始内容的: {has_original_count}/20")
        
    except Exception as e:
        logger.error(f"对比失败: {e}")


async def main():
    """主函数"""
    project_root = Path(__file__).parent.parent.parent
    
    # 文件路径
    new_dataset_path = project_root / 'evaluate_service' / 'data' / 'processed' / 'validation_events_regenerated.json'
    old_dataset_path = project_root / 'evaluate_service' / 'data' / 'processed' / 'validation_events_enhanced.json'
    report_output_path = project_root / 'evaluate_service' / 'data' / 'results' / 'data_integrity_report.json'
    
    # 验证新数据集
    verifier = DataIntegrityVerifier()
    
    if new_dataset_path.exists():
        report = verifier.verify_dataset(new_dataset_path)
        if report:
            verifier.save_report(report, report_output_path)
    else:
        logger.warning(f"新数据集不存在: {new_dataset_path}")
        logger.info("请先运行 regenerate_events.py 生成数据")
    
    # 比较新旧数据集
    if old_dataset_path.exists() and new_dataset_path.exists():
        compare_datasets(old_dataset_path, new_dataset_path)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())