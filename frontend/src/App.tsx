import { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import LandingPage from './pages/LandingPage';
import IntelligencePage from './pages/IntelligencePage';
import SearchPage from './pages/SearchPage';

export type Page = 'landing' | 'intelligence' | 'search';
export type IntelligenceTab = 'chat' | 'graph' | 'catalog';

export default function App() {
  const [page, setPage] = useState<Page>('landing');
  const [chatSeedQuestion, setChatSeedQuestion] = useState<string | null>(null);
  const [intelligenceTab, setIntelligenceTab] = useState<IntelligenceTab>('chat');

  const openIntelligence = (tab: IntelligenceTab = 'chat', seedQuestion?: string) => {
    setIntelligenceTab(tab);
    setChatSeedQuestion(seedQuestion ?? null);
    setPage('intelligence');
  };

  return (
    <AnimatePresence mode="wait">
      {page === 'landing' ? (
        <LandingPage key="landing" onEnter={() => openIntelligence('chat')} onSearch={() => setPage('search')} />
      ) : page === 'search' ? (
        <SearchPage
          key="search"
          onBack={() => setPage('landing')}
          onChat={(prefill) => openIntelligence('chat', prefill)}
          onGraph={() => openIntelligence('graph')}
          onCatalog={() => openIntelligence('catalog')}
        />
      ) : (
        <IntelligencePage
          key="intelligence"
          onBack={() => setPage('landing')}
          onSearch={() => setPage('search')}
          initialTab={intelligenceTab}
          initialQuestion={chatSeedQuestion}
        />
      )}
    </AnimatePresence>
  );
}
