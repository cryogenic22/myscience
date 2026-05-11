import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useSearchParams } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import LandingPage from './pages/LandingPage';
import WorkspacePage from './pages/WorkspacePage';
import SearchPage from './pages/SearchPage';
import NewWorkspace from './pages/NewWorkspace';
import ConnectorsPage from './pages/ConnectorsPage';
import CIPage from './pages/CIPage';
import DecisionDetailPage from './components/ci/decisions/DecisionDetailPage';
import DecisionWorkspace from './components/ci/decisions/DecisionWorkspace';
import FeedbackButton from './components/feedback/FeedbackButton';
import FeedbackWidget from './components/feedback/FeedbackWidget';
import { installDiagnostics } from './lib/diagnostics';
import { ThemeProvider } from './hooks/useTheme';

/**
 * SPEC_030 Q1 sign-off — legacy `/decisions` escape hatch.
 * `localStorage.mz_legacy_decisions === 'true'` routes /ci/decisions/:id
 * to the SPEC-021 DecisionDetailPage so users can still hit the
 * outcome-capture flow. Default routes to the SPEC_023 DecisionWorkspace.
 */
function DecisionRouteSelector() {
  const useLegacy =
    typeof window !== 'undefined' &&
    window.localStorage.getItem('mz_legacy_decisions') === 'true';
  return useLegacy ? <DecisionDetailPage /> : <DecisionWorkspace />;
}

function AppRoutes() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const seedQuestion = searchParams.get('q');

  // SPEC_030 Stage 6 fix #11 — global session-expiry listener. When any
  // API call hits 401, expectJson dispatches `mz:auth-expired`; we send
  // the user back to landing with a banner.
  useEffect(() => {
    const onExpired = () => {
      navigate('/?session=expired', { replace: true });
    };
    window.addEventListener('mz:auth-expired', onExpired);
    return () => window.removeEventListener('mz:auth-expired', onExpired);
  }, [navigate]);

  // SPEC_041 — install diagnostics ring buffers + mount the feedback
  // widget (always-listening) and pill (route-aware).
  useEffect(() => {
    installDiagnostics();
  }, []);

  return (
    <AnimatePresence mode="wait">
      <Routes>
        <Route
          path="/"
          element={
            <LandingPage
              key="landing"
              onEnter={() => navigate('/workspace')}
              onSearch={() => navigate('/search')}
              onCI={() => navigate('/ci')}
            />
          }
        />
        <Route
          path="/workspace"
          element={
            <WorkspacePage
              key="workspace"
              onBack={() => navigate('/')}
              onSearch={() => navigate('/search')}
              initialQuestion={seedQuestion}
            />
          }
        />
        <Route
          path="/search"
          element={
            <SearchPage
              key="search"
              onBack={() => navigate('/')}
              onChat={(prefill) => navigate(prefill ? `/workspace?q=${encodeURIComponent(prefill)}` : '/workspace')}
              onGraph={() => navigate('/workspace')}
              onCatalog={() => navigate('/workspace')}
            />
          }
        />
        <Route path="/newui" element={<NewWorkspace key="newui" />} />
        <Route path="/connectors" element={<ConnectorsPage key="connectors" />} />
        <Route path="/ci" element={<CIPage key="ci" />} />
        <Route path="/ci/decisions/:id" element={<DecisionRouteSelector key="decision-route" />} />
        <Route path="/ci/legacy-decisions/:id" element={<DecisionDetailPage key="decision-legacy" />} />
        {/* Catch-all → landing */}
        <Route path="*" element={<LandingPage onEnter={() => navigate('/workspace')} onSearch={() => navigate('/search')} onCI={() => navigate('/ci')} />} />
      </Routes>
      {/* SPEC_041 — feedback pill (route-aware) + the always-listening
          widget. The pill dispatches `mz:open-feedback`; the widget
          stays in the DOM but renders nothing until the event fires. */}
      <FeedbackButton />
      <FeedbackWidget />
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <ErrorBoundary>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ErrorBoundary>
    </ThemeProvider>
  );
}
