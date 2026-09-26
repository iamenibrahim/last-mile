const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function worker({ offline = false, status = 200 } = {}) {
  const handlers = {}, stored = [], deleted = [];
  const cache = {
    addAll: async () => {},
    put: async (request) => stored.push(request.url),
    match: async (request) => new Response('cached:' + request.url),
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/sw.js'), 'utf8'), {
    URL, Response,
    self: { location: { origin: 'https://example.test' },
      addEventListener: (type, handler) => handlers[type] = handler,
      skipWaiting() {}, clients: { claim() {} } },
    caches: { open: async () => cache, keys: async () => ['last-mile-v2', 'last-mile-v3', 'other-app'],
      delete: async (key) => deleted.push(key) },
    fetch: async () => { if (offline) throw new Error('offline'); return new Response('online', { status }); },
  });
  return { handlers, stored, deleted };
}

async function request(env, pathname, method = 'GET') {
  let response;
  const work = [];
  env.handlers.fetch({ request: { url: new URL(pathname, 'https://example.test').href, method },
    respondWith: (value) => response = value, waitUntil: (value) => work.push(value) });
  const result = await response;
  await Promise.all(work);
  return result;
}

test('private API, audio, query and cross-origin requests never enter automatic cache', async () => {
  const env = worker();
  for (const target of ['/api/continue/RBX-TEST0', '/api/handoff/RBX-TEST0', '/grounded/api/audio/test',
    '/?code=RBX-TEST0', 'https://elsewhere.test/', '/missing']) {
    assert.equal(await request(env, target), undefined);
  }
  assert.equal(await request(env, '/', 'POST'), undefined);
  assert.deepEqual(env.stored, []);
});

test('only successful shell responses are cached', async () => {
  const env = worker();
  assert.equal((await request(env, '/assets/app.js')).status, 200);
  assert.deepEqual(env.stored, ['https://example.test/assets/app.js']);
  const failing = worker({ status: 500 });
  assert.equal((await request(failing, '/')).status, 500);
  assert.deepEqual(failing.stored, []);
});

test('offline shell works without substituting HTML for API requests', async () => {
  const env = worker({ offline: true });
  assert.equal(await (await request(env, '/')).text(), 'cached:https://example.test/');
  assert.equal(await request(env, '/api/continue/RBX-TEST0'), undefined);
});

test('upgrade removes old app cache but preserves unrelated applications', async () => {
  const env = worker();
  let complete;
  env.handlers.activate({ waitUntil: (value) => complete = value });
  await complete;
  assert.deepEqual(env.deleted, ['last-mile-v2']);
});
