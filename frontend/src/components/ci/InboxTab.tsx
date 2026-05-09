import { useCallback, useEffect, useState } from 'react';
import { SensingFeed } from './SensingFeed';

interface Props {
  onOpenDecision: (id: string) => void;
  onOpenWarRoom: (id: string, signalKbq?: string) => void;
  onOpenSignals?: () => void;
  onOpenInsights?: () => void;
}

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

export default function InboxTab({
  onOpenDecision, onOpenWarRoom, onOpenInsights,
}: Props) {
  const authed = hasToken();

  if (!authed) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ padding: '40px' }}>
        <div className="text-center max-w-md">
          <div
            className="text-[13px] mb-4"
            style={{ color: 'var(--color-ink-3)' }}
          >
            Log in (viewer or above) to see your decision inbox.
          </div>
          <button
            type="button"
            onClick={() => { window.location.href = '/login'; }}
            className="btn-primary"
          >
            Log In
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <SensingFeed />
    </div>
  );
}
