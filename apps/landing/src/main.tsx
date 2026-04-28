import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@pulse/ui/styles.css';
import { MissionControl } from './MissionControl';

const el = document.getElementById('root');
if (!el) throw new Error('#root not found');
createRoot(el).render(
  <StrictMode>
    <MissionControl />
  </StrictMode>,
);
