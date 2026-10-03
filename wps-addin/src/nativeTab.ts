interface NativeTabHost {
  OnKey(key: string): void;
  SendKeys(keys: string, wait: boolean): void;
  ActiveWindow: { Activate(): void };
}

export function returnNativeTab(options: { app: NativeTabHost; hide: () => void; shift: boolean }) {
  options.hide();
  // Remove the override before replaying through WPS's own keyboard path, not Range.Offset.
  options.app.OnKey('{TAB}');
  options.app.ActiveWindow.Activate();
  options.app.SendKeys(options.shift ? '+{TAB}' : '{TAB}', true);
}

export function handleInlineTab(options: { ready: boolean; shift: boolean;
  complete: () => void; native: (shift: boolean) => void }) {
  if (options.ready && !options.shift) options.complete();
  else options.native(options.shift);
}
