import { useEffect, useMemo, useState } from 'react';
import { WpsHostAdapter } from '../host';
import { BusinessInlineEditor } from './BusinessInlineEditor';
import { InlineEditor } from './InlineEditor';

export function InlineRoot() {
  const host = useMemo(() => new WpsHostAdapter(), []);
  const [version, setVersion] = useState(() => host.readMetadata().schema_version);
  useEffect(() => {
    const syncVersion = () => { if (host.ready()) setVersion(host.readMetadata().schema_version); };
    window.addEventListener('presales-inline-context', syncVersion);
    let nonce = host.metadataNonce();
    const timer = window.setInterval(() => {
      const current = host.metadataNonce();
      if (nonce === current || !host.ready()) return;
      nonce = current; setVersion(host.readMetadata().schema_version);
    }, 300);
    return () => { window.clearInterval(timer); window.removeEventListener('presales-inline-context', syncVersion); };
  }, [host]);
  return version === 2 ? <BusinessInlineEditor /> : <InlineEditor />;
}
