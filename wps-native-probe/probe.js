(function (root) {
  'use strict';
  const EVENT_NAMES = ['SheetChange', 'SheetSelectionChange', 'SheetActivate',
    'WindowActivate', 'WindowDeactivate', 'WorkbookBeforeClose'];
  const CAPABILITIES = ['uncommitted_text', 'caret', 'ime', 'native_ghost',
    'edit_tab', 'native_restore', 'escape_formula', 'scroll_zoom_windows'];

  class NativeProbe {
    constructor(app, clock) {
      this.app = app;
      this.clock = clock;
      this.events = [];
      this.listeners = [];
      this.armed = false;
      this.results = Object.fromEntries(CAPABILITIES.map((key) => [key,
        { status: 'not_verified', evidence: '', steps: '' }]));
    }

    record(type, details = {}) {
      this.events.push({ sequence: this.events.length + 1, at: this.clock(), type, ...details });
    }

    start() {
      if (this.listeners.length) throw new Error('验证已开始，请先停止');
      this.record('start', { version: String(this.app.Version), build: String(this.app.Build),
        os: String(this.app.OperatingSystem) });
      try {
        for (const name of EVENT_NAMES) {
          const callback = (_sheet, target) => {
            this.record(name, { row: Number(target?.Row) || null,
              column: Number(target?.Column) || null });
            if (name === 'WorkbookBeforeClose' || name === 'WindowDeactivate') this.restore();
          };
          this.app.ApiEvent.AddApiEventListener(name, callback);
          this.listeners.push([name, callback]);
        }
      } catch (error) {
        this.record('subscription_error', { error: String(error) });
        this.stop();
        throw error;
      }
    }

    sample() {
      // Length only: a read of Value2 is evidence of a committed value, not an edit buffer API.
      try {
        const value = this.app.ActiveCell.Value2;
        this.record('committed_cell_read', { value_type: typeof value,
          value_length: String(value ?? '').length });
      } catch (error) {
        this.record('committed_cell_read_error', { error: String(error) });
        throw error;
      }
    }

    arm() {
      if (!this.listeners.length) throw new Error('先开始验证');
      this.app.OnKey('{TAB}', 'NativeProbeTab');
      this.armed = true;
      this.record('tab_registered');
    }

    tab() {
      this.record('tab_callback');
      this.restore();
      // Deliberately no SendKeys or cell writes. The first key only tests dispatch.
    }

    restore() {
      if (!this.armed) return;
      this.app.OnKey('{TAB}');
      this.armed = false;
      this.record('tab_restored');
    }

    stop() {
      this.restore();
      const failures = [];
      this.listeners = this.listeners.filter(([name, callback]) => {
        try { this.app.ApiEvent.RemoveApiEventListener(name, callback); return false; }
        catch (error) { failures.push(error); return true; }
      });
      this.record('stop', { remaining_subscriptions: this.listeners.length });
      if (failures.length) throw new Error('事件清理失败：' + failures.map(String).join('; '));
    }

    report() {
      return { schema_version: 1, evidence_scope: 'native_capability_probe',
        native_integration_enabled: false, capabilities: this.results, events: this.events };
    }
  }
  root.NativeProbe = NativeProbe;
})(globalThis);
