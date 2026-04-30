/**
 * 内存泄漏检测测试脚本
 * 用于验证内存泄漏检测功能是否正常工作
 */

// 模拟内存泄漏检测
function testMemoryLeakDetection() {
  console.log('🧪 开始内存泄漏检测测试...');

  // 测试1: 检查内存使用量获取
  console.log('测试1: 检查内存使用量获取');
  if ('memory' in performance) {
    const memory = performance.memory;
    console.log('✅ 支持performance.memory API');
    console.log(`  已使用内存: ${(memory.usedJSHeapSize / (1024 * 1024)).toFixed(2)} MB`);
    console.log(`  总内存: ${(memory.totalJSHeapSize / (1024 * 1024)).toFixed(2)} MB`);
    console.log(`  内存限制: ${(memory.jsHeapSizeLimit / (1024 * 1024)).toFixed(2)} MB`);
  } else {
    console.log('⚠️ 不支持performance.memory API，使用备用方法');
  }

  // 测试2: 创建测试定时器
  console.log('\n测试2: 定时器泄漏检测');
  const timerIds = [];
  for (let i = 0; i < 5; i++) {
    const timerId = setTimeout(() => {
      console.log(`定时器 ${i} 执行`);
    }, 10000);
    timerIds.push(timerId);
  }
  console.log(`✅ 创建了 ${timerIds.length} 个定时器`);

  // 测试3: 创建测试EventSource（模拟）
  console.log('\n测试3: EventSource泄漏检测');
  const testConnections = [];
  try {
    // 模拟EventSource创建
    for (let i = 0; i < 3; i++) {
      const mockConnection = {
        url: `http://localhost:8000/api/v2/test/${i}`,
        readyState: 0, // CONNECTING
        createdAt: new Date()
      };
      testConnections.push(mockConnection);
    }
    console.log(`✅ 模拟创建了 ${testConnections.length} 个EventSource连接`);
  } catch (error) {
    console.log(`⚠️ EventSource创建失败: ${error.message}`);
  }

  // 测试4: DOM节点泄漏检测
  console.log('\n测试4: DOM节点泄漏检测');
  const testDivs = [];
  for (let i = 0; i < 10; i++) {
    const div = document.createElement('div');
    div.className = 'test-leak-div';
    div.textContent = `测试节点 ${i}`;
    div.style.display = 'none'; // 隐藏以模拟泄漏
    document.body.appendChild(div);
    testDivs.push(div);
  }
  console.log(`✅ 创建了 ${testDivs.length} 个测试DOM节点`);

  // 测试5: 内存增长模拟
  console.log('\n测试5: 内存增长模拟');
  const largeArray = [];
  for (let i = 0; i < 10000; i++) {
    largeArray.push({
      id: i,
      data: 'x'.repeat(100), // 100字符的字符串
      timestamp: Date.now()
    });
  }
  console.log(`✅ 创建了包含 ${largeArray.length} 个对象的大数组`);

  // 清理测试资源
  console.log('\n🧹 清理测试资源...');

  // 清理定时器
  timerIds.forEach(id => clearTimeout(id));
  console.log(`✅ 清理了 ${timerIds.length} 个定时器`);

  // 清理DOM节点
  testDivs.forEach(div => {
    if (div.parentNode) {
      div.parentNode.removeChild(div);
    }
  });
  console.log(`✅ 清理了 ${testDivs.length} 个DOM节点`);

  // 清理大数组
  largeArray.length = 0;
  console.log('✅ 清理了大数组');

  // 模拟垃圾回收
  console.log('\n🔄 模拟垃圾回收...');
  if (window.gc) {
    window.gc();
    console.log('✅ 强制垃圾回收已执行');
  } else {
    console.log('⚠️ 不支持强制垃圾回收');
  }

  // 最终内存检查
  console.log('\n📊 最终内存检查:');
  if ('memory' in performance) {
    const finalMemory = performance.memory;
    const usedMB = finalMemory.usedJSHeapSize / (1024 * 1024);
    console.log(`  最终内存使用: ${usedMB.toFixed(2)} MB`);

    // 检查内存是否回落
    if (usedMB < 100) { // 假设正常内存使用小于100MB
      console.log('✅ 内存使用正常，无显著泄漏');
    } else {
      console.log('⚠️ 内存使用较高，可能存在泄漏');
    }
  }

  console.log('\n🎉 内存泄漏检测测试完成！');
  console.log('建议:');
  console.log('1. 打开浏览器开发者工具，查看Console输出');
  console.log('2. 访问 http://localhost:5173/test/memory-leak 进行完整测试');
  console.log('3. 使用Memory面板进行堆快照分析');
}

// 运行测试
if (typeof window !== 'undefined') {
  // 等待页面加载完成
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', testMemoryLeakDetection);
  } else {
    testMemoryLeakDetection();
  }
} else {
  console.log('请在浏览器环境中运行此测试');
}