/**
 * 内存泄漏测试页面
 * 用于验证SSE连接内存泄漏修复效果
 */

import { MemoryLeakTestPanel } from '../../components/MemoryLeakTestPanel';

export function MemoryLeakTestPage() {
  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>内存泄漏测试</h1>
      <p>此页面用于测试SSE连接内存泄漏修复效果。</p>

      <div style={{ marginTop: '30px' }}>
        <MemoryLeakTestPanel />
      </div>

      <div style={{ marginTop: '40px', padding: '20px', backgroundColor: '#f8f9fa', borderRadius: '8px' }}>
        <h3>测试说明</h3>
        <p>这个测试面板包含以下功能：</p>
        <ul>
          <li><strong>内存使用监控</strong>: 实时显示当前内存使用情况、增长量和增长率</li>
          <li><strong>SSE泄漏测试</strong>: 故意创建SSE连接但不清理，测试泄漏检测机制</li>
          <li><strong>定时器泄漏测试</strong>: 创建定时器但不清理，测试定时器泄漏检测</li>
          <li><strong>自动清理</strong>: 清理所有测试资源，验证内存回收效果</li>
          <li><strong>结果导出</strong>: 导出测试结果为JSON文件</li>
        </ul>

        <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#fff3cd', borderRadius: '5px' }}>
          <h4 style={{ color: '#856404' }}>测试步骤</h4>
          <ol>
            <li>点击"检查内存"按钮查看初始内存状态</li>
            <li>点击"SSE泄漏测试"创建5个SSE连接</li>
            <li>观察内存增长情况</li>
            <li>点击"清理所有测试"按钮</li>
            <li>再次点击"检查内存"验证内存是否回落</li>
            <li>重复测试验证稳定性</li>
          </ol>
          <p style={{ marginTop: '10px', color: '#856404' }}>
            预期结果：清理后内存应回落，SSE连接数归零，无持续内存增长。
          </p>
        </div>
      </div>

      <div style={{ marginTop: '30px', fontSize: '14px', color: '#6c757d' }}>
        <p><strong>注意：</strong>这些测试会故意创建内存泄漏，请在测试完成后务必点击"清理所有测试"按钮。</p>
        <p>内存泄漏检测器每10秒自动检查一次，检测到泄漏会在控制台输出警告。</p>
      </div>
    </div>
  );
}