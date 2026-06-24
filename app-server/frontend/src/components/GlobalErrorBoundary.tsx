import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props { children: ReactNode; }
interface State { hasError: boolean; error: Error | null; errorInfo: ErrorInfo | null; }

export class GlobalErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    console.error('Global React Error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
          <h1 style={{ color: 'red' }}>系统发生未捕获的渲染异常</h1>
          <p>非常抱歉，应用程序崩溃。请刷新页面，或将以下信息截屏报告开发人员：</p>
          <pre style={{ background: '#f4f4f4', padding: '1rem', borderRadius: '8px', overflowX: 'auto', fontSize: '13px' }}>
            {this.state.error && this.state.error.toString()}
            <br />
            {this.state.errorInfo?.componentStack}
          </pre>
          <button 
            onClick={() => window.location.reload()} 
            style={{ padding: '8px 16px', background: '#3b82f6', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', marginTop: '1rem' }}
          >
            强制刷新页面
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
