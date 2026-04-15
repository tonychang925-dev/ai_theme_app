import React from 'react';

export function TestPage() {
  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      <h1>测试页面 - 选股器</h1>
      <p>如果这个页面能显示，说明React基础工作正常。</p>

      <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#f0f0f0', borderRadius: '5px' }}>
        <h3>系统状态:</h3>
        <ul>
          <li>React应用: ✅ 运行中</li>
          <li>Vite开发服务器: ✅ 运行中</li>
          <li>页面路由: ✅ 工作正常</li>
        </ul>
      </div>

      <div style={{ marginTop: '20px' }}>
        <h3>下一步测试:</h3>
        <button
          onClick={() => {
            fetch('/api/stock-screener/strategies')
              .then(res => res.json())
              .then(data => alert(`获取到 ${data.length} 个策略`))
              .catch(err => alert(`API错误: ${err.message}`));
          }}
          style={{ padding: '10px 20px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
        >
          测试API连接
        </button>
      </div>
    </div>
  );
}