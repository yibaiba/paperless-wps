import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MetadataRecords, readMetadataRecords, writeMetadataRecords } from '../src/metadataRecords.ts';

for (const failure of ['root', 'record']) {
  test(`${failure} write failure cannot poison reads after another page reuses unpublished rows`, () => {
    const cells = new Map();
    let failing = false;
    const adapter = { read: (row) => cells.get(row) ?? '', write: (row, value) => {
      const reject = failure === 'root' ? row === 1 : value.includes('presales-records-v2');
      if (failing && reject) throw new Error('unpublished write rejected');
      cells.set(row, value);
    } };
    const inline = new MetadataRecords(adapter);
    const pane = new MetadataRecords(adapter);
    const original = { schema_version: 2, workbook_instance_id: 'original', line_bindings: [] };
    writeMetadataRecords(inline, original);
    failing = true;
    assert.throws(() => writeMetadataRecords(inline, { ...original, workbook_instance_id: 'failed' }), /rejected/);
    assert.deepEqual(readMetadataRecords(pane), original);
    failing = false;
    const committed = { ...original, workbook_instance_id: 'committed' };
    writeMetadataRecords(pane, committed);
    assert.deepEqual(readMetadataRecords(inline), committed);
    // A later write from the previously failed page must also compare against committed data.
    writeMetadataRecords(inline, { ...original, workbook_instance_id: 'failed' });
    assert.equal(readMetadataRecords(pane).workbook_instance_id, 'failed');
  });
}
