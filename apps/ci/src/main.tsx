import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@mz/ui/styles.css';
import { CIShell } from './CIShell';

const el = document.getElementById('root');
if (!el) throw new Error('#root not found');
createRoot(el).render(
  <StrictMode>
    <CIShell />
  </StrictMode>,
);
