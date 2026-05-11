import { useEffect, useRef, useState } from 'react';

/**
 * PB-401 — Brief autosave hook.
 *
 * Debounces `doc` changes by `delayMs` (default 4000) and posts to
 * `/decision-briefs/{briefId}`. BE-19 (`POST /briefs/{id}`) is not
 * yet merged — until it lands, this hook returns the `Saved` /
 * `Saving…` indicator and logs to console without making a network
 * call. When BE-19 ships, replace the body of `persistDraft` with
 * a real fetch.
 */

export type AutosaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export interface UseBriefAutosaveResult {
  status: AutosaveStatus;
  /** Force-save now (called by the Save button). */
  saveNow: () => Promise<void>;
}

async function persistDraft(briefId: string, doc: unknown): Promise<void> {
  // TODO(BE-19): replace with
  //   await fetch(`${BASE}/decision-briefs/${briefId}`, {
  //     method: 'POST',
  //     headers: { 'Content-Type': 'application/json', ...authHeaders() },
  //     body: JSON.stringify({ doc }),
  //   });
  if (typeof console !== 'undefined' && process?.env?.NODE_ENV !== 'test') {
    // eslint-disable-next-line no-console
    console.debug('[BriefAutosave] would POST', briefId, doc);
  }
}

export function useBriefAutosave(
  briefId: string,
  doc: unknown,
  delayMs: number = 4000,
): UseBriefAutosaveResult {
  const [status, setStatus] = useState<AutosaveStatus>('saved');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const firstRun = useRef(true);

  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    setStatus('saving');
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      persistDraft(briefId, doc)
        .then(() => setStatus('saved'))
        .catch(() => setStatus('error'));
    }, delayMs);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [briefId, doc, delayMs]);

  const saveNow = async (): Promise<void> => {
    if (timer.current) clearTimeout(timer.current);
    setStatus('saving');
    try {
      await persistDraft(briefId, doc);
      setStatus('saved');
    } catch {
      setStatus('error');
    }
  };

  return { status, saveNow };
}
