type Measurement = 'workbench-module' | 'engine-module' | 'initialize' | 'rendered' | 'projection' | 'edit-request' | 'dispose';
type Detail = Readonly<Record<string, number | boolean>>;

// Opt-in diagnostic builds only; never record business values or identifiers.
export function startSheetMeasure(name: Measurement) {
  const enabled = import.meta.env.VITE_SHEET_PERFORMANCE === '1';
  const start = enabled ? performance.now() : 0;
  return (detail: Detail = {}) => {
    if (enabled) performance.measure(`quotation-sheet:${name}`, { start, end: performance.now(), detail });
  };
}
