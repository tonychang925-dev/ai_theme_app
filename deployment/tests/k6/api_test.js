/**
 * AI主题分析应用 - API性能测试脚本
 * 使用k6进行性能压力测试
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// 自定义指标
const errorRate = new Rate('errors');
const responseTimeTrend = new Trend('response_times');

// 测试配置
export const options = {
  stages: [
    // 预热阶段
    { duration: '1m', target: 10 },
    // 逐步增加负载
    { duration: '3m', target: 50 },
    { duration: '3m', target: 100 },
    // 峰值负载
    { duration: '5m', target: 150 },
    // 逐步减少负载
    { duration: '2m', target: 50 },
    { duration: '1m', target: 10 },
    { duration: '1m', target: 0 },
  ],
  thresholds: {
    // 全局阈值
    'http_req_duration': ['p(95)<500', 'p(99)<1000'],
    'http_req_failed': ['rate<0.01'], // 错误率小于1%
    'errors': ['rate<0.01'],
  },
  ext: {
    loadimpact: {
      name: 'AI Theme App - API Performance Test',
    },
  },
};

// 测试数据
const themeIds = [
  'theme_001', 'theme_002', 'theme_003', 'theme_004', 'theme_005',
  'theme_006', 'theme_007', 'theme_008', 'theme_009', 'theme_010'
];

const stockCodes = [
  '000001', '000002', '000858', '600519', '300750',
  '002415', '300059', '600036', '000333', '000651'
];

const searchTerms = ['科技', '消费', '医药', '新能源', '人工智能', '金融', '制造', '环保'];

// 随机选择函数
function getRandomThemeId() {
  return themeIds[Math.floor(Math.random() * themeIds.length)];
}

function getRandomStockCode() {
  return stockCodes[Math.floor(Math.random() * stockCodes.length)];
}

function getRandomSearchTerm() {
  return searchTerms[Math.floor(Math.random() * searchTerms.length)];
}

function getRandomDate() {
  const today = new Date();
  const pastDate = new Date(today);
  pastDate.setDate(today.getDate() - Math.floor(Math.random() * 7));
  return pastDate.toISOString().split('T')[0];
}

// 主测试函数
export default function () {
  // 用户ID用于跟踪
  const userId = __VU * 1000 + __ITER;

  // 测试组1: 主题相关API
  group('Theme APIs', function () {
    // 获取主题列表
    const themesParams = {
      limit: Math.floor(Math.random() * 20) + 5,
      page: Math.floor(Math.random() * 5) + 1,
      sort_by: ['heat', 'created_at', 'updated_at'][Math.floor(Math.random() * 3)]
    };

    const themesRes = http.get('http://localhost:8000/api/themes', {
      params: themesParams,
      tags: { api: 'themes_list', user: userId.toString() }
    });

    check(themesRes, {
      '主题列表状态码200': (r) => r.status === 200,
      '主题列表响应时间<500ms': (r) => r.timings.duration < 500,
    }) || errorRate.add(1);

    responseTimeTrend.add(themesRes.timings.duration);

    // 获取主题详情
    const themeId = getRandomThemeId();
    const themeDetailRes = http.get(`http://localhost:8000/api/themes/${themeId}`, {
      tags: { api: 'theme_detail', user: userId.toString() }
    });

    check(themeDetailRes, {
      '主题详情状态码200': (r) => r.status === 200,
      '主题详情响应时间<300ms': (r) => r.timings.duration < 300,
    }) || errorRate.add(1);

    responseTimeTrend.add(themeDetailRes.timings.duration);

    // 搜索主题
    const searchTerm = getRandomSearchTerm();
    const searchRes = http.get('http://localhost:8000/api/themes/search', {
      params: { q: searchTerm, limit: 10 },
      tags: { api: 'theme_search', user: userId.toString() }
    });

    check(searchRes, {
      '主题搜索状态码200': (r) => r.status === 200,
      '主题搜索响应时间<400ms': (r) => r.timings.duration < 400,
    }) || errorRate.add(1);

    responseTimeTrend.add(searchRes.timings.duration);

    sleep(Math.random() * 2 + 1);
  });

  // 测试组2: 情报流API
  group('Intel APIs', function () {
    const intelParams = {
      limit: Math.floor(Math.random() * 20) + 10,
      type: ['all', 'news', 'event', 'theme_update'][Math.floor(Math.random() * 4)],
      source: ['all', 'realtime', 'jyhf'][Math.floor(Math.random() * 3)]
    };

    const intelRes = http.get('http://localhost:8000/api/intel/feed', {
      params: intelParams,
      tags: { api: 'intel_feed', user: userId.toString() }
    });

    check(intelRes, {
      '情报流状态码200': (r) => r.status === 200,
      '情报流响应时间<600ms': (r) => r.timings.duration < 600,
    }) || errorRate.add(1);

    responseTimeTrend.add(intelRes.timings.duration);

    sleep(Math.random() * 1 + 0.5);
  });

  // 测试组3: 股票API
  group('Stock APIs', function () {
    const stockCode = getRandomStockCode();
    const stockRes = http.get(`http://localhost:8000/api/stocks/${stockCode}`, {
      tags: { api: 'stock_info', user: userId.toString() }
    });

    check(stockRes, {
      '股票信息状态码200': (r) => r.status === 200,
      '股票信息响应时间<400ms': (r) => r.timings.duration < 400,
    }) || errorRate.add(1);

    responseTimeTrend.add(stockRes.timings.duration);

    sleep(Math.random() * 1 + 0.5);
  });

  // 测试组4: 复盘API
  group('Recap APIs', function () {
    const date = getRandomDate();
    const recapRes = http.get('http://localhost:8000/api/recap/daily', {
      params: { date: date },
      tags: { api: 'daily_recap', user: userId.toString() }
    });

    check(recapRes, {
      '每日复盘状态码200': (r) => r.status === 200,
      '每日复盘响应时间<800ms': (r) => r.timings.duration < 800,
    }) || errorRate.add(1);

    responseTimeTrend.add(recapRes.timings.duration);

    sleep(Math.random() * 3 + 2);
  });

  // 测试组5: AI事件处理API (高负载)
  if (Math.random() < 0.3) { // 30%的用户执行高负载操作
    group('AI Processing APIs', function () {
      const eventTemplates = [
        "公司发布新产品，预计将带动相关产业链发展",
        "政策出台支持产业发展，相关企业受益",
        "行业龙头业绩超预期，板块整体上涨",
        "技术创新突破，推动产业升级",
        "市场需求增长，供应紧张价格上涨"
      ];

      const eventContent = eventTemplates[Math.floor(Math.random() * eventTemplates.length)];

      const payload = JSON.stringify({
        content: eventContent,
        source: 'test',
        timestamp: Date.now(),
        metadata: {
          test_user: true,
          load_test: true,
          user_id: userId
        }
      });

      const headers = {
        'Content-Type': 'application/json',
        'X-Test-User': userId.toString()
      };

      const aiRes = http.post('http://localhost:8000/api/events/process', payload, {
        headers: headers,
        tags: { api: 'ai_processing', user: userId.toString() }
      });

      check(aiRes, {
        'AI处理状态码200或202': (r) => r.status === 200 || r.status === 202,
        'AI处理响应时间<2000ms': (r) => r.timings.duration < 2000,
      }) || errorRate.add(1);

      responseTimeTrend.add(aiRes.timings.duration);

      sleep(Math.random() * 2 + 1);
    });
  }
}

// 测试初始化函数
export function setup() {
  console.log('AI主题分析应用 - API性能测试开始');
  console.log('测试配置:', JSON.stringify(options, null, 2));
  console.log('测试数据准备完成');
  console.log('='.repeat(60));
}

// 测试清理函数
export function teardown(data) {
  console.log('='.repeat(60));
  console.log('AI主题分析应用 - API性能测试结束');
  console.log('测试完成时间:', new Date().toISOString());
}

// 自定义处理函数
export function handleSummary(data) {
  const summary = {
    '测试概述': {
      '测试名称': 'AI Theme App API Performance Test',
      '测试时间': new Date().toISOString(),
      '总请求数': data.metrics.http_reqs.values.count,
      '总测试时长': `${data.state.testRunDuration / 1000}秒`,
      '平均响应时间': `${data.metrics.http_req_duration.values.avg.toFixed(2)}ms`,
      'P95响应时间': `${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms`,
      '错误率': `${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%`,
      '吞吐量': `${data.metrics.http_reqs.values.rate.toFixed(2)} reqs/s`,
    },
    '阈值检查': {
      '响应时间P95<500ms': data.metrics.http_req_duration.values['p(95)'] < 500 ? '通过' : '失败',
      '错误率<1%': data.metrics.http_req_failed.values.rate < 0.01 ? '通过' : '失败',
    },
    '建议': []
  };

  // 根据测试结果生成建议
  if (data.metrics.http_req_duration.values['p(95)'] > 500) {
    summary.建议.push('P95响应时间超过500ms，建议优化慢查询或增加缓存');
  }

  if (data.metrics.http_req_failed.values.rate > 0.01) {
    summary.建议.push('错误率超过1%，建议检查服务稳定性和错误处理');
  }

  if (data.metrics.http_reqs.values.rate < 50) {
    summary.建议.push('吞吐量较低，建议优化并发处理能力');
  }

  return {
    'stdout': JSON.stringify(summary, null, 2),
    'summary.json': JSON.stringify(summary, null, 2),
  };
}