/**
 * SPEC_041 — diagnostics module.
 *
 * Captures console errors and failed fetches into ring buffers (max 50
 * each, FIFO eviction). collectDiagnostics() snapshots the buffers +
 * page metadata at submit time. clearDiagnostics() empties them after
 * a successful submit.
 *
 * Install once at App mount via installDiagnostics(). The `installed`
 * guard makes a second call a no-op so the ring buffers don't get
 * double-wrapped.
 */

import type { FeedbackDiagnosticContext } from '../api';

const MAX_ENTRIES = 50;

interface ErrorEntry {
  ts: string;
  message: string;
  stack?: string;
}

interface FailedRequestEntry {
  ts: string;
  method: string;
  url: string;
  status?: number;
  body?: string;
}

let installed = false;
let errors: ErrorEntry[] = [];
let failedRequests: FailedRequestEntry[] = [];

// References to whatever we WRAPPED at install time + the wrappers we
// installed. Reset restores ONLY if the current value is still our
// wrapper — otherwise a test-side `vi.stubGlobal('fetch', ...)` that
// fired after install would be undone by reset.
let prevConsoleError: typeof console.error | null = null;
let prevFetch: typeof fetch | null = null;
let installedConsoleError: typeof console.error | null = null;
let installedFetch: typeof fetch | null = null;

function pushCapped<T>(buf: T[], item: T): T[] {
  buf.push(item);
  if (buf.length > MAX_ENTRIES) buf.splice(0, buf.length - MAX_ENTRIES);
  return buf;
}

function nowIso(): string {
  return new Date().toISOString();
}

function detectTheme(): 'light' | 'dark' {
  if (typeof document === 'undefined') return 'light';
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

function detectDensity(): 'spacious' | 'compact' | undefined {
  if (typeof window === 'undefined') return undefined;
  const v = window.localStorage.getItem('mz_density');
  if (v === 'compact') return 'compact';
  if (v === 'spacious') return 'spacious';
  return undefined;
}

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.toString();
  return (input as Request).url;
}

function methodOf(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return init.method.toUpperCase();
  if (input instanceof Request) return input.method.toUpperCase();
  return 'GET';
}

export function installDiagnostics(): void {
  if (installed) return;
  installed = true;

  if (typeof window === 'undefined') return;

  // ─ console.error wrap ─
  const origError = console.error;
  prevConsoleError = origError;
  const wrappedError = (...args: unknown[]) => {
    try {
      const message = args
        .map((a) =>
          a instanceof Error
            ? a.message
            : typeof a === 'string'
              ? a
              : (() => {
                  try {
                    return JSON.stringify(a);
                  } catch {
                    return String(a);
                  }
                })(),
        )
        .join(' ');
      const stack = args.find((a) => a instanceof Error) as Error | undefined;
      pushCapped(errors, {
        ts: nowIso(),
        message,
        stack: stack?.stack,
      });
    } catch {
      /* never let diagnostics break console.error itself */
    }
    return origError.apply(console, args as []);
  };
  console.error = wrappedError;
  installedConsoleError = wrappedError;

  // ─ window.fetch wrap. Capture from globalThis (vi.stubGlobal touches
  // globalThis.fetch directly; jsdom's window.fetch may have a separate
  // property descriptor that doesn't pick up the stub). Wrap goes onto
  // both so any caller path (window.fetch, globalThis.fetch, plain
  // fetch()) hits the same wrapper.
  const origFetch = (globalThis as { fetch: typeof fetch }).fetch;
  prevFetch = origFetch;
  const wrappedFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = urlOf(input);
    const method = methodOf(input, init);
    try {
      const r = await origFetch(input, init);
      if (!r.ok) {
        let body: string | undefined;
        try {
          body = (await r.clone().text()).slice(0, 500);
        } catch {
          body = undefined;
        }
        pushCapped(failedRequests, {
          ts: nowIso(),
          method,
          url,
          status: r.status,
          body,
        });
      }
      return r;
    } catch (e) {
      pushCapped(failedRequests, {
        ts: nowIso(),
        method,
        url,
        body: e instanceof Error ? e.message : String(e),
      });
      throw e;
    }
  };
  (globalThis as { fetch: typeof fetch }).fetch = wrappedFetch as typeof fetch;
  if (typeof window !== 'undefined') {
    window.fetch = wrappedFetch as typeof fetch;
  }
  installedFetch = wrappedFetch as typeof fetch;

  // ─ window.onerror — uncaught runtime errors ─
  window.addEventListener('error', (e) => {
    pushCapped(errors, {
      ts: nowIso(),
      message: e.message,
      stack: e.error?.stack,
    });
  });
  window.addEventListener('unhandledrejection', (e) => {
    pushCapped(errors, {
      ts: nowIso(),
      message: `Unhandled rejection: ${e.reason?.message ?? String(e.reason)}`,
      stack: e.reason?.stack,
    });
  });
}

export function collectDiagnostics(): FeedbackDiagnosticContext {
  return {
    errors: errors.slice(),
    failed_requests: failedRequests.slice(),
    user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown',
    viewport:
      typeof window !== 'undefined'
        ? { w: window.innerWidth, h: window.innerHeight }
        : { w: 0, h: 0 },
    theme: detectTheme(),
    density: detectDensity(),
    route: typeof window !== 'undefined' ? window.location.pathname : '/',
  };
}

export function clearDiagnostics(): void {
  errors = [];
  failedRequests = [];
}

/**
 * Test-only helper. Restores the wrapped originals ONLY when we
 * previously wrapped them, so that test-side `vi.stubGlobal('fetch',
 * mockFetch)` calls are not clobbered. Then clears the installed flag
 * + buffers so the next install runs cleanly.
 */
export function __resetDiagnosticsForTests(): void {
  if (installed) {
    // Only restore if our wrapper is still in place. If a test stubbed
    // the global AFTER install (e.g. vi.stubGlobal('fetch', mock)),
    // our wrapper is no longer there — leave the test's stub alone.
    if (
      typeof console !== 'undefined' &&
      prevConsoleError &&
      console.error === installedConsoleError
    ) {
      console.error = prevConsoleError;
    }
    if (
      prevFetch &&
      (globalThis as { fetch: typeof fetch }).fetch === installedFetch
    ) {
      (globalThis as { fetch: typeof fetch }).fetch = prevFetch;
      if (typeof window !== 'undefined') window.fetch = prevFetch;
    }
  }
  installed = false;
  prevConsoleError = null;
  prevFetch = null;
  installedConsoleError = null;
  installedFetch = null;
  errors = [];
  failedRequests = [];
}
