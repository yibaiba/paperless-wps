import assert from 'node:assert/strict';
import test from 'node:test';

import { requirePanelConfiguration } from '../src/completionProtocol.ts';

test('panel completion rejects a slim inline response instead of hiding protocol mismatch', () => {
  assert.throws(
    () => requirePanelConfiguration({ items: [], issues: [], versions: {}, local_revision: 0 }),
    /任务窗格响应缺少完整业务配置/,
  );
  const configuration = { rooms: [], systems: [], requirements: [], devices: [] };
  assert.equal(
    requirePanelConfiguration({
      items: [], issues: [], versions: {}, local_revision: 0,
      configuration, line_bindings: [],
    }),
    configuration,
  );
});
