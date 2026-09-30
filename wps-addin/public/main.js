(function () {
  'use strict';

  var paneId = '';
  var tabSessionKey = 'presales_tab_session';
  var dialogKey = 'presales_inline_dialog_id';
  var backgroundErrorKey = 'presales_background_error';
  var diagnosticSessionKey = 'presales_diagnostic_session_id';

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

  function restoreNativeTab(message, replay) {
    var store = storage();
    if (store) {
      store.setItem(tabSessionKey, '');
      if (message) store.setItem(backgroundErrorKey, message);
    }
    if (typeof window.Application.OnKey === 'function') {
      window.Application.OnKey('{TAB}');
    }
    if (replay && typeof window.Application.SendKeys === 'function') {
      window.Application.SendKeys('{TAB}');
    }
  }

  window.PresalesTab = function () {
    try {
      var store = storage();
      var session = store && JSON.parse(store.getItem(tabSessionKey) || 'null');
      if (!session || session.status !== 'ready') {
        restoreNativeTab('', true);
        return false;
      }
      var dialogId = Number(store.getItem(dialogKey) || 0);
      var dialog = dialogId && window.Application.GetWebDialog(dialogId);
      if (!dialog || typeof dialog.ExecuteJavaScript !== 'function') {
        restoreNativeTab('Tab 补全窗口不可用，已恢复 WPS 原生 Tab', true);
        return false;
      }
      dialog.ExecuteJavaScript(
        'window.PresalesInlineTab && window.PresalesInlineTab('
        + JSON.stringify(session.session_id) + ')'
      );
      return true;
    } catch (error) {
      var detail = error && error.message ? error.message : String(error);
      restoreNativeTab('Tab 补全失败：' + detail, true);
      return false;
    }
  };

  window.OnAddinLoad = function (ribbonUI) {
    if (typeof window.Application.ribbonUI !== 'object') {
      window.Application.ribbonUI = ribbonUI;
    }
    var store = storage();
    if (store && window.crypto && typeof window.crypto.randomUUID === 'function') {
      store.setItem(diagnosticSessionKey, window.crypto.randomUUID());
    }
    restoreNativeTab('', false);
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
