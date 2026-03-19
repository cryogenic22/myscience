import { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import LandingPage from './pages/LandingPage';
import WorkspacePage from './pages/WorkspacePage';
import SearchPage from './pages/SearchPage';

export type Page = 'landing' | 'workspace' | 'search';

export default function App() {
  const [page, setPage] = useState<Page>('landing');
  const [chatSeedQuestion, setChatSeedQuestion] = useState<string | null>(null);

  const openWorkspace = (seedQuestion?: string) => {
    setChatSeedQuestion(seedQuestion ?? null);
    setPage('workspace');
  };

  return (
    <AnimatePresence mode="wait">
      {page === 'landing' ? (
        <LandingPage key="landing" onEnter={() => openWorkspace()} onSearch={() => setPage('search')} />
      ) : page === 'search' ? (
        <SearchPage
          key="search"
          onBack={() => setPage('landing')}
          onChat={(prefill) => openWorkspace(prefill)}
          onGraph={() => openWorkspace()}
          onCatalog={() => openWorkspace()}
        />
      ) : (
        <WorkspacePage
          key="workspace"
          onBack={() => setPage('landing')}
          onSearch={() => setPage('search')}
          initialQuestion={chatSeedQuestion}
        />
      )}
    </AnimatePresence>
  );
}
