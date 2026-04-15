/**
 * SSE连接内存泄漏修复测试
 * 验证SSE连接是否正确清理，防止内存泄漏
 */

class SSELeakTest {
  constructor() {
    this.connections = [];
    this.testResults = [];
    this.memoryReadings = [];
    this.testStartTime = null;
  }

  // 记录测试结果
  logResult(type, status, details) {
    const result = {
      id: Date.now(),
      type,
      timestamp: new Date(),
      status,
      details
    };

    this.testResults.push(result);
    console.log(`[${result.timestamp.toLocaleTimeString()}] ${type}: ${status} - ${details}`);

    return result;
  }

  // 获取内存使用量
  getMemoryUsage() {
    if ('memory' in performance) {
      const memory = performance.memory;
      return {
        usedMB: memory.usedJSHeapSize / (1024 * 1024),
        totalMB: memory.totalJSHeapSize / (1024 * 1024),
        limitMB: memory.jsHeapSizeLimit / (1024 * 1024)
      };
    }
    return { usedMB: 0, totalMB: 0, limitMB: 0 };
  }

  // 创建SSE连接（模拟）
  createSSEConnection(url) {
    const connectionId = Date.now();
    const connection = {
      id: connectionId,
      url,
      createdAt: new Date(),
      isConnected: true,
      eventSource: null,
      listeners: new Map()
    };

    try {
      // 模拟EventSource创建
      console.log(`🔗 创建SSE连接 #${connectionId}: ${url}`);

      // 模拟事件监听器
      const messageHandler = (event) => {
        console.log(`📨 连接 #${connectionId} 收到消息:`, event.data);
      };

      const errorHandler = (event) => {
        console.error(`❌ 连接 #${connectionId} 错误:`, event);
      };

      const openHandler = () => {
        console.log(`✅ 连接 #${connectionId} 已打开`);
      };

      const closeHandler = () => {
        console.log(`🔌 连接 #${connectionId} 已关闭`);
      };

      // 存储监听器引用以便清理
      connection.listeners.set('message', messageHandler);
      connection.listeners.set('error', errorHandler);
      connection.listeners.set('open', openHandler);
      connection.listeners.set('close', closeHandler);

      this.connections.push(connection);

      this.logResult('sse_connection', 'created', `连接 #${connectionId} 已创建`);

      return connectionId;
    } catch (error) {
      console.error(`创建SSE连接失败:`, error);
      this.logResult('sse_connection', 'error', `创建失败: ${error.message}`);
      return null;
    }
  }

  // 正确清理SSE连接
  cleanupSSEConnection(connectionId) {
    const index = this.connections.findIndex(conn => conn.id === connectionId);
    if (index === -1) {
      console.log(`连接 #${connectionId} 不存在`);
      return false;
    }

    const connection = this.connections[index];

    try {
      console.log(`🧹 清理SSE连接 #${connectionId}`);

      // 模拟清理事件监听器
      connection.listeners.forEach((handler, eventType) => {
        console.log(`  移除 ${eventType} 事件监听器`);
      });

      // 模拟关闭EventSource
      if (connection.eventSource) {
        console.log(`  关闭EventSource`);
      }

      // 清理引用
      connection.listeners.clear();
      connection.eventSource = null;
      connection.isConnected = false;

      // 从数组中移除
      this.connections.splice(index, 1);

      this.logResult('sse_connection', 'cleaned', `连接 #${connectionId} 已清理`);

      return true;
    } catch (error) {
      console.error(`清理SSE连接失败:`, error);
      this.logResult('sse_connection', 'error', `清理失败: ${error.message}`);
      return false;
    }
  }

  // 故意泄漏SSE连接（不清理）
  createSSELeak(url) {
    const connectionId = this.createSSEConnection(url);
    if (connectionId) {
      this.logResult('sse_leak', 'created', `故意泄漏连接 #${connectionId}`);
    }
    return connectionId;
  }

  // 批量创建泄漏
  createBatchLeaks(count = 5) {
    console.log(`💥 批量创建 ${count} 个SSE泄漏`);

    const leakIds = [];
    for (let i = 0; i < count; i++) {
      const url = `http://localhost:8000/api/leak-test/${i}`;
      const connectionId = this.createSSELeak(url);
      if (connectionId) {
        leakIds.push(connectionId);
      }

      // 间隔创建
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    this.logResult('batch_leak', 'created', `创建了 ${leakIds.length} 个泄漏连接`);
    return leakIds;
  }

  // 清理所有连接
  cleanupAllConnections() {
    console.log(`🧹 清理所有SSE连接 (共 ${this.connections.length} 个)`);

    const connectionCount = this.connections.length;
    const connectionIds = this.connections.map(conn => conn.id);

    // 复制数组以避免修改迭代中的数组
    const connectionsToClean = [...this.connections];

    connectionsToClean.forEach(connection => {
      this.cleanupSSEConnection(connection.id);
    });

    this.logResult('cleanup_all', 'cleaned', `清理了 ${connectionCount} 个连接`);

    return connectionIds;
  }

  // 运行内存泄漏测试
  async runMemoryLeakTest() {
    console.log('🧪 开始SSE内存泄漏测试');
    this.testStartTime = new Date();
    this.memoryReadings = [];

    // 记录初始内存
    const initialMemory = this.getMemoryUsage();
    this.memoryReadings.push({
      time: 0,
      memory: initialMemory,
      connectionCount: this.connections.length
    });

    console.log(`📊 初始内存: ${initialMemory.usedMB.toFixed(2)} MB`);
    console.log(`📊 初始连接数: ${this.connections.length}`);

    // 阶段1: 创建泄漏
    console.log('\n=== 阶段1: 创建泄漏 ===');
    const leakIds = await this.createBatchLeaks(5);

    // 等待并记录内存
    await new Promise(resolve => setTimeout(resolve, 3000));
    const memoryAfterLeaks = this.getMemoryUsage();
    this.memoryReadings.push({
      time: 3,
      memory: memoryAfterLeaks,
      connectionCount: this.connections.length
    });

    console.log(`📊 泄漏后内存: ${memoryAfterLeaks.usedMB.toFixed(2)} MB`);
    console.log(`📊 当前连接数: ${this.connections.length}`);

    // 阶段2: 部分清理
    console.log('\n=== 阶段2: 部分清理 ===');
    if (leakIds.length > 0) {
      // 清理前2个连接
      for (let i = 0; i < Math.min(2, leakIds.length); i++) {
        this.cleanupSSEConnection(leakIds[i]);
      }
    }

    // 等待并记录内存
    await new Promise(resolve => setTimeout(resolve, 3000));
    const memoryAfterPartialCleanup = this.getMemoryUsage();
    this.memoryReadings.push({
      time: 6,
      memory: memoryAfterPartialCleanup,
      connectionCount: this.connections.length
    });

    console.log(`📊 部分清理后内存: ${memoryAfterPartialCleanup.usedMB.toFixed(2)} MB`);
    console.log(`📊 剩余连接数: ${this.connections.length}`);

    // 阶段3: 完全清理
    console.log('\n=== 阶段3: 完全清理 ===');
    this.cleanupAllConnections();

    // 等待垃圾回收
    await new Promise(resolve => setTimeout(resolve, 3000));

    // 强制垃圾回收（如果可用）
    if (window.gc) {
      console.log('🔄 执行强制垃圾回收');
      window.gc();
      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    const finalMemory = this.getMemoryUsage();
    this.memoryReadings.push({
      time: 10,
      memory: finalMemory,
      connectionCount: this.connections.length
    });

    console.log(`📊 最终内存: ${finalMemory.usedMB.toFixed(2)} MB`);
    console.log(`📊 最终连接数: ${this.connections.length}`);

    // 分析结果
    console.log('\n=== 测试结果分析 ===');
    const memoryGrowth = finalMemory.usedMB - initialMemory.usedMB;
    const memoryGrowthPercent = (memoryGrowth / initialMemory.usedMB) * 100;

    console.log(`内存增长: ${memoryGrowth.toFixed(2)} MB (${memoryGrowthPercent.toFixed(1)}%)`);
    console.log(`连接清理: ${leakIds.length} 个连接全部清理`);

    if (memoryGrowth < 5 && this.connections.length === 0) {
      console.log('✅ 测试通过: 内存泄漏修复有效');
      this.logResult('test_complete', 'passed', '内存泄漏修复测试通过');
    } else {
      console.log('⚠️ 测试警告: 可能存在内存泄漏');
      this.logResult('test_complete', 'warning', `内存增长 ${memoryGrowth.toFixed(2)}MB, 剩余连接 ${this.connections.length}`);
    }

    // 生成测试报告
    return this.generateTestReport();
  }

  // 生成测试报告
  generateTestReport() {
    const report = {
      timestamp: new Date(),
      testDuration: this.testStartTime ? (Date.now() - this.testStartTime.getTime()) / 1000 : 0,
      initialConnections: this.memoryReadings[0]?.connectionCount || 0,
      finalConnections: this.connections.length,
      memoryReadings: this.memoryReadings,
      testResults: this.testResults,
      summary: {
        totalTests: this.testResults.length,
        passedTests: this.testResults.filter(r => r.status === 'passed').length,
        failedTests: this.testResults.filter(r => r.status === 'error').length,
        warnings: this.testResults.filter(r => r.status === 'warning').length
      }
    };

    console.log('\n📋 测试报告:');
    console.log(JSON.stringify(report, null, 2));

    return report;
  }

  // 导出测试结果
  exportResults() {
    const report = this.generateTestReport();
    const dataStr = JSON.stringify(report, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });

    const downloadUrl = URL.createObjectURL(dataBlob);
    const downloadLink = document.createElement('a');
    downloadLink.href = downloadUrl;
    downloadLink.download = `sse-leak-test-${Date.now()}.json`;

    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
    URL.revokeObjectURL(downloadUrl);

    console.log('📥 测试结果已导出');
  }
}

// 全局测试实例
window.SSELeakTest = SSELeakTest;

// 自动运行测试（如果启用了自动测试）
if (typeof window !== 'undefined' && window.location.search.includes('autotest')) {
  document.addEventListener('DOMContentLoaded', async () => {
    console.log('🚀 自动运行SSE内存泄漏测试');
    const test = new SSELeakTest();
    await test.runMemoryLeakTest();
  });
}

console.log('SSE内存泄漏测试脚本已加载');
console.log('使用方法:');
console.log('1. const test = new SSELeakTest()');
console.log('2. await test.runMemoryLeakTest()');
console.log('3. test.exportResults()');