import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onRetry?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

const FEEDBACK_URL = (import.meta.env.DEV ? '/api' : '') + '/feedback';

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Fire-and-forget — log crash to /feedback endpoint
    fetch(FEEDBACK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category: 'bug',
        title: `UI crash: ${error.message?.slice(0, 120) ?? 'Unknown error'}`,
        description: error.stack ?? String(error),
        priority: 'high',
        page_url: typeof window !== 'undefined' ? window.location.href : undefined,
        diagnostic_context: {
          componentStack: info.componentStack ?? null,
        },
      }),
    }).catch(() => {
      // Silently ignore network failures — we must not block rendering
    });
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
          Something went wrong. Refresh to continue.
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
