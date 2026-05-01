import { BrowserRouter, Routes, Route, useNavigate, useSearchParams } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import LandingPage from './pages/LandingPage';
import WorkspacePage from './pages/WorkspacePage';
import SearchPage from './pages/SearchPage';
import NewWorkspace from './pages/NewWorkspace';
import ConnectorsPage from './pages/ConnectorsPage';

function AppRoutes() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const seedQuestion = searchParams.get('q');

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
        {/* Catch-all → landing */}
        <Route path="*" element={<LandingPage onEnter={() => navigate('/workspace')} onSearch={() => navigate('/search')} />} />
      </Routes>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ErrorBoundary>
  );
}
