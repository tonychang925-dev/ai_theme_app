/**
 * AI Theme App - k6性能测试脚本
 * 现代负载测试工具，支持复杂测试场景
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// 自定义指标
const errorRate = new Rate('errors');
const requestDuration = new Trend('request_duration');
const totalRequests = new Counter('total_requests');

// 测试配置
export const options = {
  stages: [
    // 预热阶段
    { duration: '30s', target: 10 },
    // 正常负载阶段
    { duration: '2m', target: 50 },
    // 峰值负载阶段
    { duration: '1m', target: 100 },
    // 恢复阶段
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    // 95%的请求响应时间应小于500ms
    'request_duration': ['p(95)<500'],
    // 错误率应小于1%
    'errors': ['rate<0.01'],
    // 检查成功率
    'checks': ['rate>0.99'],
  },
};

// 测试数据
const themes = [
  '人工智能', '大数据', '云计算', '区块链', '物联网',
  '5G通信', '新能源汽车', '生物医药', '半导体', '金融科技'
];

const stocks = [
  { code: '000001', name: '平安银行' },
  { code: '000002', name: '万科A' },
  { code: '000858', name: '五粮液' },
  { code: '002415', name: '海康威视' },
  { code: '300750', name: '宁德时代' }
];

const newsKeywords = [
  '财报', '业绩', '增长', '下跌', '收购',
  '合作', '创新', '政策', '市场', '投资'
];

// 基础URL
const BASE_URL = __ENV.TEST_BASE_URL || 'http://localhost:8000';

// 辅助函数：获取随机元素
function getRandomElement(array) {
  return array[Math.floor(Math.random() * array.length)];
}

// 辅助函数：生成随机日期
function getRandomDate(daysAgo) {
  const date = new Date();
  date.setDate(date.getDate() - Math.floor(Math.random() * daysAgo));
  return date.toISOString().split('T')[0];
}

// 测试场景：主题分析
export function themeAnalysisScenario() {
  group('主题分析场景', function() {
    // 1. 获取主题列表
    const themesResponse = http.get(`${BASE_URL}/api/themes`);
    check(themesResponse, {
      '获取主题列表成功': (r) => r.status === 200,
      '响应时间小于200ms': (r) => r.timings.duration < 200,
    });
    errorRate.add(themesResponse.status !== 200);
    requestDuration.add(themesResponse.timings.duration);
    totalRequests.add(1);
    sleep(1);

    // 2. 分析特定主题
    const theme = getRandomElement(themes);
    const analyzePayload = JSON.stringify({
      theme: theme,
      time_range: '7d',
      analysis_depth: 'medium'
    });
    const analyzeResponse = http.post(
      `${BASE_URL}/api/themes/analyze`,
      analyzePayload,
      { headers: { 'Content-Type': 'application/json' } }
    );
    check(analyzeResponse, {
      '主题分析成功': (r) => r.status === 200 || r.status === 202,
      '响应时间小于1000ms': (r) => r.timings.duration < 1000,
    });
    errorRate.add(analyzeResponse.status !== 200 && analyzeResponse.status !== 202);
    requestDuration.add(analyzeResponse.timings.duration);
    totalRequests.add(1);
    sleep(2);

    // 3. 获取主题详情
    const detailsResponse = http.get(`${BASE_URL}/api/themes/${theme}`);
    check(detailsResponse, {
      '获取主题详情成功': (r) => r.status === 200,
      '响应时间小于300ms': (r) => r.timings.duration < 300,
    });
    errorRate.add(detailsResponse.status !== 200);
    requestDuration.add(detailsResponse.timings.duration);
    totalRequests.add(1);
    sleep(1);
  });
}

// 测试场景：新闻流处理
export function newsStreamScenario() {
  group('新闻流处理场景', function() {
    // 1. 获取新闻流
    const category = getRandomElement(['all', 'financial', 'tech', 'market']);
    const newsResponse = http.get(
      `${BASE_URL}/api/news/stream?limit=20&offset=0&category=${category}`
    );
    check(newsResponse, {
      '获取新闻流成功': (r) => r.status === 200,
      '响应时间小于300ms': (r) => r.timings.duration < 300,
    });
    errorRate.add(newsResponse.status !== 200);
    requestDuration.add(newsResponse.timings.duration);
    totalRequests.add(1);
    sleep(1);

    // 2. 搜索新闻
    const keyword = getRandomElement(newsKeywords);
    const searchPayload = JSON.stringify({
      keyword: keyword,
      start_date: getRandomDate(7),
      end_date: getRandomDate(1)
    });
    const searchResponse = http.post(
      `${BASE_URL}/api/news/search`,
      searchPayload,
      { headers: { 'Content-Type': 'application/json' } }
    );
    check(searchResponse, {
      '搜索新闻成功': (r) => r.status === 200,
      '响应时间小于500ms': (r) => r.timings.duration < 500,
    });
    errorRate.add(searchResponse.status !== 200);
    requestDuration.add(searchResponse.timings.duration);
    totalRequests.add(1);
    sleep(1);

    // 3. 分析新闻情感（模拟）
    const newsId = Math.floor(Math.random() * 1000) + 1;
    const sentimentResponse = http.get(
      `${BASE_URL}/api/news/${newsId}/sentiment`
    );
    check(sentimentResponse, {
      '分析新闻情感成功': (r) => r.status === 200,
      '响应时间小于400ms': (r) => r.timings.duration < 400,
    });
    errorRate.add(sentimentResponse.status !== 200);
    requestDuration.add(sentimentResponse.timings.duration);
    totalRequests.add(1);
    sleep(1);
  });
}

// 测试场景：市场分析
export function marketAnalysisScenario() {
  group('市场分析场景', function() {
    // 1. 获取市场指标
    const indicatorsResponse = http.get(`${BASE_URL}/api/market/indicators`);
    check(indicatorsResponse, {
      '获取市场指标成功': (r) => r.status === 200,
      '响应时间小于400ms': (r) => r.timings.duration < 400,
    });
    errorRate.add(indicatorsResponse.status !== 200);
    requestDuration.add(indicatorsResponse.timings.duration);
    totalRequests.add(1);
    sleep(1);

    // 2. 获取股票分析
    const stock = getRandomElement(stocks);
    const stockResponse = http.get(
      `${BASE_URL}/api/stocks/${stock.code}/analysis`
    );
    check(stockResponse, {
      '获取股票分析成功': (r) => r.status === 200,
      '响应时间小于600ms': (r) => r.timings.duration < 600,
    });
    errorRate.add(stockResponse.status !== 200);
    requestDuration.add(stockResponse.timings.duration);
    totalRequests.add(1);
    sleep(2);

    // 3. 获取异常信号
    const signalType = getRandomElement(['price', 'volume', 'sentiment']);
    const signalsResponse = http.get(
      `${BASE_URL}/api/signals/abnormal?signal_type=${signalType}&threshold=0.8`
    );
    check(signalsResponse, {
      '获取异常信号成功': (r) => r.status === 200,
      '响应时间小于500ms': (r) => r.timings.duration < 500,
    });
    errorRate.add(signalsResponse.status !== 200);
    requestDuration.add(signalsResponse.timings.duration);
    totalRequests.add(1);
    sleep(1);
  });
}

// 测试场景：用户认证
export function authScenario() {
  group('用户认证场景', function() {
    // 1. 用户登录
    const username = `test_user_${Math.floor(Math.random() * 1000) + 1}`;
    const loginPayload = JSON.stringify({
      username: username,
      password: 'test_password'
    });
    const loginResponse = http.post(
      `${BASE_URL}/api/auth/login`,
      loginPayload,
      { headers: { 'Content-Type': 'application/json' } }
    );
    check(loginResponse, {
      '用户登录成功': (r) => r.status === 200,
      '响应时间小于300ms': (r) => r.timings.duration < 300,
      '返回有效token': (r) => {
        try {
          const data = JSON.parse(r.body);
          return data.token && data.token.length > 0;
        } catch {
          return false;
        }
      }
    });
    errorRate.add(loginResponse.status !== 200);
    requestDuration.add(loginResponse.timings.duration);
    totalRequests.add(1);

    // 提取token用于后续请求
    let token = '';
    try {
      const data = JSON.parse(loginResponse.body);
      token = data.token || '';
    } catch (e) {
      console.warn('Failed to parse login response');
    }

    sleep(1);

    // 2. 使用token访问受保护资源
    if (token) {
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      // 访问用户信息
      const profileResponse = http.get(
        `${BASE_URL}/api/auth/profile`,
        { headers: headers }
      );
      check(profileResponse, {
        '获取用户信息成功': (r) => r.status === 200,
        '响应时间小于200ms': (r) => r.timings.duration < 200,
      });
      errorRate.add(profileResponse.status !== 200);
      requestDuration.add(profileResponse.timings.duration);
      totalRequests.add(1);
    }

    sleep(1);

    // 3. 用户登出
    const logoutResponse = http.post(
      `${BASE_URL}/api/auth/logout`,
      null,
      { headers: { 'Content-Type': 'application/json' } }
    );
    check(logoutResponse, {
      '用户登出成功': (r) => r.status === 200,
      '响应时间小于200ms': (r) => r.timings.duration < 200,
    });
    errorRate.add(logoutResponse.status !== 200);
    requestDuration.add(logoutResponse.timings.duration);
    totalRequests.add(1);
    sleep(1);
  });
}

// 测试场景：综合工作流
export function completeWorkflowScenario() {
  group('完整工作流场景', function() {
    // 模拟完整用户工作流
    authScenario();
    sleep(1);

    // 随机选择1-2个分析场景
    const scenarios = [
      themeAnalysisScenario,
      newsStreamScenario,
      marketAnalysisScenario
    ];

    const selectedScenarios = [];
    const count = Math.floor(Math.random() * 2) + 1; // 1-2个场景

    for (let i = 0; i < count; i++) {
      const scenario = getRandomElement(scenarios);
      if (!selectedScenarios.includes(scenario)) {
        selectedScenarios.push(scenario);
        scenario();
        sleep(2);
      }
    }
  });
}

// 主测试函数
export default function() {
  // 随机选择测试场景
  const scenarios = [
    { weight: 3, func: themeAnalysisScenario },      // 30% 主题分析
    { weight: 3, func: newsStreamScenario },         // 30% 新闻流处理
    { weight: 2, func: marketAnalysisScenario },     // 20% 市场分析
    { weight: 1, func: authScenario },               // 10% 用户认证
    { weight: 1, func: completeWorkflowScenario }    // 10% 完整工作流
  ];

  // 根据权重选择场景
  const totalWeight = scenarios.reduce((sum, s) => sum + s.weight, 0);
  let random = Math.random() * totalWeight;

  for (const scenario of scenarios) {
    random -= scenario.weight;
    if (random <= 0) {
      scenario.func();
      break;
    }
  }
}

// 测试生命周期钩子
export function setup() {
  console.log('性能测试开始');
  console.log(`目标URL: ${BASE_URL}`);
  console.log('测试配置:', JSON.stringify(options, null, 2));

  // 返回测试上下文
  return {
    startTime: new Date().toISOString(),
    baseUrl: BASE_URL
  };
}

export function teardown(data) {
  console.log('性能测试结束');
  console.log(`开始时间: ${data.startTime}`);
  console.log(`结束时间: ${new Date().toISOString()}`);
  console.log(`目标URL: ${data.baseUrl}`);

  // 这里可以添加测试结果上报逻辑
  // 例如：发送到监控系统、保存到数据库等
}

// 导出测试场景供单独使用
export {
  themeAnalysisScenario,
  newsStreamScenario,
  marketAnalysisScenario,
  authScenario,
  completeWorkflowScenario
};