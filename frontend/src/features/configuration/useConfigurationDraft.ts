import { useRef, useState } from "react";
import type { Configuration } from "./types";

export function useConfigurationDraft(initial: Configuration, initialHistoryKey = '') {
  type Entry = { configuration: Configuration; historyKey: string };
  const [present, setPresent] = useState(initial);
  const [historyKey, setHistoryKey] = useState(initialHistoryKey);
  const currentHistoryKey = useRef(initialHistoryKey);
  const current = useRef(initial);
  const past = useRef<Entry[]>([]), future = useRef<Entry[]>([]);
  const [version, setVersion] = useState(0);
  const replaceCurrent = (next: Configuration, nextHistoryKey = currentHistoryKey.current) => {
    current.current = next;
    currentHistoryKey.current = nextHistoryKey;
    setHistoryKey(nextHistoryKey);
    setPresent(next);
    setVersion((v) => v + 1);
  };
  const commit = (next: Configuration, nextHistoryKey = currentHistoryKey.current) => {
    if (JSON.stringify(next) === JSON.stringify(current.current) && nextHistoryKey === currentHistoryKey.current) return;
    past.current.push({ configuration: current.current, historyKey: currentHistoryKey.current });
    future.current = [];
    replaceCurrent(next, nextHistoryKey);
  };
  const move = (back: boolean) => {
    const from = back ? past : future,
      to = back ? future : past;
    const next = from.current.pop();
    if (!next) return;
    to.current.push({ configuration: current.current, historyKey: currentHistoryKey.current });
    replaceCurrent(next.configuration, next.historyKey);
  };
  return {
    present,
    current,
    version,
    historyKey,
    currentHistoryKey,
    commit,
    replaceCurrent,
    undo: () => move(true),
    redo: () => move(false),
    canUndo: past.current.length > 0,
    canRedo: future.current.length > 0,
  };
}
