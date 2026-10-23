import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker from './_worker.js';

test('static assets use the Pages asset binding', async () => {
  const response = await worker.fetch(new Request('https://app.example/'), { ASSETS: { fetch: () => new Response('app') } });
  assert.equal(await response.text(), 'app');
});
test('hardware paths cannot be forwarded by the public site', async () => {
  assert.equal((await worker.fetch(new Request('https://app.example/api/device/bins/ELM-01/session'), {})).status, 404);
});
test('missing and invalid API hosts produce explicit configuration errors', async () => {
  for (const origin of [undefined, 'http://localhost:8000', 'https://api.example/private', 'https://user:secret@api.example']) {
    assert.equal((await worker.fetch(new Request('https://app.example/api/health'), { API_ORIGIN: origin })).status, 503);
  }
});
test('proxy preserves API path, search and resident auth without forwarding device credentials', async () => {
  const original = globalThis.fetch;
  let sent;
  globalThis.fetch = async (target, options) => { sent = { target: String(target), options }; return Response.json({ ok: true }); };
  try {
    const response = await worker.fetch(new Request('https://app.example/api/leaderboard?scope=townships', { headers: { Authorization: 'Bearer resident-test', 'X-Device-Key': 'must-not-leave', Cookie: 'private=1' } }), { API_ORIGIN: 'https://api.example' });
    assert.equal(sent.target, 'https://api.example/api/leaderboard?scope=townships');
    assert.equal(sent.options.headers.get('Authorization'), 'Bearer resident-test');
    assert.equal(sent.options.headers.get('X-Device-Key'), null);
    assert.equal(sent.options.headers.get('Cookie'), null);
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
    assert.equal(response.status, 200);
  } finally { globalThis.fetch = original; }
});
test('API outages yield a readable 502', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('offline'); };
  try { assert.equal((await worker.fetch(new Request('https://app.example/api/health'), { API_ORIGIN: 'https://api.example' })).status, 502); }
  finally { globalThis.fetch = original; }
});
