import assert from 'node:assert/strict';
import { test } from 'node:test';

import { CredentialStore } from '../src/credentialStore.ts';

function storage(values = []) {
  const items = new Map(values);
  return {
    items,
    getItem: (key) => items.get(key),
    setItem: (key, value) => items.set(key, String(value)),
  };
}

test('persistent credentials are restored into WPS shared storage', () => {
  const shared = storage();
  const persistent = storage([
    ['presales_access_token', 'saved-token'],
    ['presales_account', '售前一号'],
  ]);
  const credentials = new CredentialStore({ shared, persistent });

  credentials.restore();

  assert.equal(credentials.token(), 'saved-token');
  assert.equal(shared.items.get('presales_access_token'), 'saved-token');
  assert.equal(shared.items.get('presales_account'), '售前一号');
});

test('new credentials update persistent and shared stores together', () => {
  const shared = storage();
  const persistent = storage();
  const credentials = new CredentialStore({
    shared, persistent, identifier: () => 'installation-1',
  });

  credentials.saveToken('new-token');
  credentials.saveAccount('售前二号');

  assert.equal(shared.items.get('presales_access_token'), 'new-token');
  assert.equal(persistent.items.get('presales_access_token'), 'new-token');
  assert.equal(credentials.installationId(), 'installation-1');
  assert.equal(credentials.installationId(), 'installation-1');
});

test('missing persistent storage is an explicit compatibility issue', () => {
  const credentials = new CredentialStore({ shared: storage() });
  assert.deepEqual(credentials.capabilityIssues(), ['localStorage']);
  assert.throws(() => credentials.saveToken('token'), /localStorage/);
});
