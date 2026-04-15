import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null
    };
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      error,
      errorInfo: null
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('React错误边界捕获:', error, errorInfo);
    this.setState({
      error,
      errorInfo
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif', color: '#721c24', backgroundColor: '#f8d7da', border: '1px solid #f5c6cb', borderRadius: '5px', margin: '20px' }}>
          <h2>应用出错</h2>
          <p>页面渲染时发生错误。请检查浏览器控制台获取详细信息。</p>

          {this.state.error && (
            <div style={{ marginTop: '10px', padding: '10px', backgroundColor: '#fff', borderRadius: '3px' }}>
              <strong>错误信息:</strong>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: '12px' }}>{this.state.error.toString()}</pre>
            </div>
          )}

          <button
            onClick={() => window.location.reload()}
            style={{ marginTop: '15px', padding: '8px 16px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            刷新页面
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}