export interface SheetChange {
  sheet: string; row: number; column: number; rowCount: number; columnCount: number;
  structural: boolean;
}
type Callback = (...args: any[]) => void;
interface EventApi {
  AddApiEventListener(name: string, handler: Callback): void;
  RemoveApiEventListener(name: string, handler: Callback): void;
}

// Registry is page-local: WPS owns separate listener lifetimes for separate web pages.
const registries = new WeakMap<object, Map<string, { callbacks: Set<Callback>; handler: Callback }>>();
export function subscribeHostEvent(api: EventApi, name: string, callback: Callback) {
  let registry = registries.get(api);
  if (!registry) { registry = new Map(); registries.set(api, registry); }
  let entry = registry.get(name);
  if (!entry) {
    const callbacks = new Set<Callback>();
    entry = { callbacks, handler: (...args) => callbacks.forEach((fn) => fn(...args)) };
    api.AddApiEventListener(name, entry.handler);
    registry.set(name, entry);
  }
  entry.callbacks.add(callback);
  return () => {
    entry!.callbacks.delete(callback);
    if (entry!.callbacks.size) return;
    api.RemoveApiEventListener(name, entry!.handler);
    registry!.delete(name);
  };
}

export function sheetChange(sheet: any, target: any): SheetChange {
  const address = typeof target?.Address === 'function' ? target.Address() : target?.Address;
  return {
    sheet: String(sheet?.Name ?? ''), row: Number(target?.Row ?? 0),
    column: Number(target?.Column ?? 0), rowCount: Number(target?.Rows?.Count ?? 0),
    columnCount: Number(target?.Columns?.Count ?? 0),
    structural: !target || !target.Row || /^\$?\d+:\$?\d+$/.test(String(address))
      || /^\$?[A-Z]+:\$?[A-Z]+$/.test(String(address)),
  };
}
