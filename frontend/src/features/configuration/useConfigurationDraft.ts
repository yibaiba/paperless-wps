import { useRef, useState } from "react";
import type { Configuration } from "./types";

export function useConfigurationDraft(initial: Configuration) {
  const [present, setPresent] = useState(initial);
  const current = useRef(initial);
  const past = useRef<Configuration[]>([]),
    future = useRef<Configuration[]>([]);
  const [version, setVersion] = useState(0);
  const commit = (next: Configuration) => {
    if (JSON.stringify(next) === JSON.stringify(current.current)) return;
    past.current.push(current.current);
    future.current = [];
    current.current = next;
    setPresent(next);
    setVersion((v) => v + 1);
  };
  const move = (back: boolean) => {
    const from = back ? past : future,
      to = back ? future : past;
    const next = from.current.pop();
    if (!next) return;
    to.current.push(current.current);
    current.current = next;
    setPresent(next);
    setVersion((v) => v + 1);
  };
  return {
    present,
    current,
    version,
    commit,
    undo: () => move(true),
    redo: () => move(false),
    canUndo: past.current.length > 0,
    canRedo: future.current.length > 0,
  };
}
