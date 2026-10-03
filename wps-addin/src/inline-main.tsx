import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { InlineRoot } from './components/InlineRoot';
import './inline.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode><InlineRoot /></StrictMode>,
);
