/**
 * 格式化工具函数
 */

/**
 * 格式化数字，保留指定位数小数
 * @param value 输入值
 * @param digits 小数位数，默认2
 * @returns 格式化后的字符串
 */
export function formatNumber(value: unknown, digits: number = 2): string {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n.toFixed(digits) : '--';
}

/**
 * 格式化亿单位数字
 * @param value 输入值
 * @returns 格式化后的字符串，如 "1.23亿"
 */
export function formatBillion(value: unknown): string {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? `${(n / 1e8).toFixed(2)}亿` : '--';
}

/**
 * 将数字转换为数值（用于排序和计算）
 * @param value 输入值
 * @returns 转换后的数字，非数字返回0
 */
export function toNumber(value: unknown): number {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

/**
 * 将英文阶段名称翻译为中文
 * @param value 英文阶段名称
 * @returns 中文阶段名称
 */
export function translateStage(value: string): string {
  const stageMap: Record<string, string> = {
    'start': '启动',
    'fermentation': '发酵',
    'divergence': '分歧',
    'rebound': '弱转强',
    'climax': '高潮',
    'fade': '退潮',
    'main': '主线',
    'strong_branch': '强分支'
  };

  return value.split('_').map(part => stageMap[part] || part).join('');
}

/**
 * 格式化日期（仅月日）
 * @param value 日期字符串
 * @returns 格式化的月日字符串，如 "04-10"
 */
export function formatDateOnly(value: string): string {
  if (!value) return '--';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
  });
}

/**
 * 格式化日期时间（月日时分）
 * @param value 日期字符串
 * @returns 格式化的日期时间字符串，如 "04-10 14:30"
 */
export function formatDateTime(value: string): string {
  if (!value) return '--';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * 格式化发生时间（智能判断）
 * @param occurredAt 发生时间
 * @param itemType 项目类型
 * @returns 格式化后的时间字符串
 */
export function formatOccurredAt(occurredAt: string, itemType?: string): string {
  if (!occurredAt) return '--';
  const d = new Date(occurredAt);
  if (Number.isNaN(d.getTime())) return occurredAt;

  const isMidnight = d.getHours() === 0 && d.getMinutes() === 0;
  if (itemType === 'new_theme' && isMidnight) {
    return formatDateOnly(occurredAt);
  }

  return formatDateTime(occurredAt);
}

/**
 * 格式化置信度
 * @param confidence 置信度值
 * @returns 格式化后的字符串
 */
export function formatConfidence(confidence: number | null | undefined): string {
  if (confidence == null) return '--';
  return formatNumber(confidence, 2);
}

/**
 * 格式化影响分数
 * @param impactScore 影响分数
 * @returns 格式化后的字符串
 */
export function formatImpactScore(impactScore: number | null | undefined): string {
  if (impactScore == null) return '--';
  return formatNumber(impactScore, 0);
}

/**
 * 获取项目色调
 * @param itemType 项目类型
 * @returns 色调名称
 */
export function getItemTone(itemType: string): string {
  if (itemType === 'event_review') return 'signal';
  if (itemType === 'new_theme') return 'spark';
  if (itemType === 'theme_move' || itemType === 'stock_move') return 'heat';
  return 'signal';
}

/**
 * 获取项目类型标签
 * @param itemType 项目类型
 * @returns 中文标签
 */
export function getItemTypeLabel(itemType: string): string | null {
  if (itemType === 'event_review') return '待复核';
  if (itemType === 'event') return '新事件';
  if (itemType === 'new_theme') return '新题材';
  return null;
}

/**
 * 获取来源类型标签
 * @param sourceType 来源类型
 * @returns 中文标签
 */
export function getSourceLabel(sourceType: string): string {
  const sourceMap: Record<string, string> = {
    'event_theme_map': '题材匹配事件',
    'event_review_queue': '人工复核队列',
    'jyhf_history': '久赢驱动事件',
    'jyhf_rank_daily': '久赢榜单异动',
    'jyhf_stock_daily': '久赢股票异动',
    'jyhf_full_theme_list': '久赢题材列表',
  };

  return sourceMap[sourceType] || sourceType;
}
