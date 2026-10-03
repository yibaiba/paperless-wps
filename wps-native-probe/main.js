(function () {
  'use strict';
  let probe;
  window.OnAddinLoad = function () {
    probe = new NativeProbe(window.Application, () => new Date().toISOString());
    return true;
  };
  window.NativeProbeTab = function () { probe.tab(); };
  window.OnAction = function (control) {
    try {
      if (control.Id === 'start') probe.start();
      if (control.Id === 'sample') probe.sample();
      if (control.Id === 'arm') probe.arm();
      if (control.Id === 'stop') probe.stop();
      if (control.Id === 'report') {
        probe.stop();
        const url = URL.createObjectURL(new Blob([JSON.stringify(probe.report(), null, 2)],
          { type: 'application/json' }));
        const link = document.createElement('a');
        link.href = url; link.download = 'wps-native-probe.json'; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      return true;
    } catch (error) { alert(String(error)); return false; }
  };
})();
