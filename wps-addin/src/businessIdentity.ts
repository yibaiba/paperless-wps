// Same UUID v5 namespace and name as the server's workbook-line identity.
export async function deviceIdForLine(bindingId: string, lineId: string): Promise<string> {
  const namespace = Uint8Array.from('6ba7b8119dad11d180b400c04fd430c8'.match(/../g)!, (v) => parseInt(v, 16));
  const name = new TextEncoder().encode(`presales-wps-device:${bindingId}:${lineId}`);
  const bytes = new Uint8Array(namespace.length + name.length);
  bytes.set(namespace); bytes.set(name, namespace.length);
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-1', bytes)).slice(0, 16);
  hash[6] = (hash[6] & 0x0f) | 0x50; hash[8] = (hash[8] & 0x3f) | 0x80;
  const hex = [...hash].map((v) => v.toString(16).padStart(2, '0')).join('');
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
}
