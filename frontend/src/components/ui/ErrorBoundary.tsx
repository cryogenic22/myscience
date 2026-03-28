import { Component, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onRetry?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null });
    this.props.onRetry?.();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    if (this.props.fallback) {
      return this.props.fallback;
    }

    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '32px 24px',
          borderRadius: '16px',
          background: 'var(--color-red-soft)',
          fontFamily: 'var(--font-body)',
          textAlign: 'center',
          gap: '8px',
        }}
      >
        <div
          style={{
            fontSize: '14px',
            fontWeight: 600,
            color: 'var(--color-red)',
          }}
        >
          Something went wrong
        </div>
        <div
          style={{
            fontSize: '12px',
            color: 'var(--color-ink-3)',
            maxWidth: '320px',
            lineHeight: 1.5,
          }}
        >
          This section encountered an error
        </div>
        <button
          type="button"
          onClick={this.handleRetry}
          style={{
            marginTop: '8px',
            padding: '8px 18px',
            borderRadius: '980px',
            border: 'none',
            background: 'var(--color-red)',
            color: '#fff',
            fontSize: '13px',
            fontWeight: 500,
            fontFamily: 'var(--font-body)',
            cursor: 'pointer',
            transition: 'opacity 160ms ease',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '0.85'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
        >
          Try again
        </button>
      </div>
    );
  }
}
