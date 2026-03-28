import { useCallback, useState } from 'react';
import type { ToastItem, ToastProps } from '../components/ui/Toast';

export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const show = useCallback(
    (
      message: string,
      variant: ToastProps['variant'] = 'info',
      action?: { label: string; onClick: () => void },
      duration?: number,
    ) => {
      const id = crypto.randomUUID();
      setToasts(prev => [...prev, { id, message, variant, action, duration }]);
      return id;
    },
    [],
  );

  const dismiss = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return { toasts, show, dismiss };
}
