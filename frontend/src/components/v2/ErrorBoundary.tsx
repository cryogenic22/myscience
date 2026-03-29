import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  onRetry?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
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
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: 200,
          padding: 'var(--space-6)',
        }}
      >
        <div
          style={{
            maxWidth: 360,
            width: '100%',
            backgroundColor: 'var(--surface-secondary)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-8)',
            textAlign: 'center',
            boxShadow: 'var(--shadow-md)',
          }}
        >
          {/* Error icon */}
          <div
            style={{
              width: 48,
              height: 48,
              margin: '0 auto var(--space-4)',
              borderRadius: '50%',
              backgroundColor: 'var(--confidence-low)',
              opacity: 0.15,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative',
            }}
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              style={{ position: 'absolute', top: 12, left: 12 }}
            >
              <path
                d="M12 9v4m0 4h.01M12 3l9.66 16.59A1 1 0 0 1 20.77 21H3.23a1 1 0 0 1-.89-1.41L12 3z"
                stroke="var(--confidence-low)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>

          {/* Title */}
          <h3
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-xl)',
              fontWeight: 600,
              color: 'var(--text-primary)',
              margin: '0 0 var(--space-2)',
            }}
          >
            Something went wrong
          </h3>

          {/* Error detail */}
          {this.state.error && (
            <p
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-sm)',
                color: 'var(--text-secondary)',
                margin: '0 0 var(--space-6)',
                lineHeight: 1.5,
              }}
            >
              {this.state.error.message}
            </p>
          )}

          {/* Retry button */}
          <button
            type="button"
            onClick={this.handleRetry}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-base)',
              fontWeight: 500,
              padding: 'var(--space-2) var(--space-5)',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--accent)',
              color: '#ffffff',
              border: 'none',
              cursor: 'pointer',
              transition: `background-color var(--duration-fast) var(--ease-out)`,
            }}
          >
            Try again
          </button>
        </div>
      </div>
    );
  }
}
