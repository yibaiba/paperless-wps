import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { InlineEditor } from './components/InlineEditor';
import './inline.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode><InlineEditor /></StrictMode>,
);
