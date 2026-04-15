// 测试API响应格式
async function testAPIResponse() {
  console.log('🔍 测试API响应格式...');

  try {
    const response = await fetch('http://localhost:8003/api/stock-screener/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        strategy_id: 'default_composite',
        trade_date: '2026-04-10',
        limit: 3,
        enable_llm_review: false,
        llm_top_k: 3
      })
    });

    const data = await response.json();

    console.log('✅ API响应成功');
    console.log('状态码:', response.status);
    console.log('响应状态:', data.status);
    console.log('job_id:', data.job_id);
    console.log('results长度:', data.results ? data.results.length : 0);

    if (data.results && data.results.length > 0) {
      console.log('第一条结果结构:');
      console.log(JSON.stringify(data.results[0], null, 2));

      // 检查关键字段
      const firstResult = data.results[0];
      console.log('\n关键字段检查:');
      console.log('  result_id:', firstResult.result_id);
      console.log('  stock_id:', firstResult.stock_id);
      console.log('  stock_name:', firstResult.stock_name);
      console.log('  composite_score:', firstResult.composite_score);
      console.log('  dimension_scores:', firstResult.dimension_scores);
      console.log('  rank_position:', firstResult.rank_position);
      console.log('  screening_reason:', firstResult.screening_reason);
      console.log('  theme_info:', firstResult.theme_info);
    } else {
      console.log('⚠️ API返回空结果');
    }

    // 检查前端期望的字段
    console.log('\n前端期望字段匹配检查:');
    const expectedFields = [
      'result_id', 'stock_id', 'stock_name', 'composite_score',
      'dimension_scores', 'rank_position', 'screening_reason'
    ];

    if (data.results && data.results.length > 0) {
      const firstResult = data.results[0];
      expectedFields.forEach(field => {
        const hasField = field in firstResult;
        console.log(`  ${field}: ${hasField ? '✅' : '❌'} ${hasField ? firstResult[field] : '缺失'}`);
      });
    }

  } catch (error) {
    console.error('❌ API测试失败:', error.message);
  }
}

// 运行测试
testAPIResponse();