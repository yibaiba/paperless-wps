(function () {
  'use strict';

  var paneId = '';

  function storage() {
    return window.Application && window.Application.PluginStorage;
  }

  function baseUrl() {
    return window.location.href.replace(/(?:index\.html)?(?:[?#].*)?$/, '');
  }

  function showPane(action) {
    var store = storage();
    if (store) store.setItem('presales_requested_action', action || 'open');
    var id = paneId || (store && store.getItem('presales_taskpane_id'));
    var pane = null;
    if (id) {
      try { pane = window.Application.GetTaskPane(id); }
      catch (error) { pane = null; }
    }
    if (!pane) {
      pane = window.Application.CreateTaskPane(baseUrl() + 'taskpane.html');
      if (!pane) throw new Error('WPS 未能创建任务窗格');
      paneId = pane.ID;
      if (store && paneId) store.setItem('presales_taskpane_id', paneId);
    }
    pane.DockPosition = 2;
    pane.Visible = true;
    return true;
  }

  window.OnAddinLoad = function (ribbonUI) {
    if (typeof window.Application.ribbonUI !== 'object') {
      window.Application.ribbonUI = ribbonUI;
    }
    return true;
  };

  window.OnAction = function (control) {
    try {
      return showPane(control && control.Id);
    } catch (error) {
      alert(error && error.message ? error.message : String(error));
      return false;
    }
  };

})();
