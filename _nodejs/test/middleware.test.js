// Offline tests for _nodejs/index.js, run with `node --test _nodejs/test`.
//
// The middleware runs as a child process in a temp working directory, because it reads and writes
// `_share/settings.json` relative to the working directory (index.js:15). Its ports are fixed (index.js:10-11),
// so the tests check that 8042 and 8021 are free first. Remote mode always points at a local websocket server.
//
// Known bugs are strict expected failures: only an assertion failure counts, and a passing body fails the test,
// so a fix shows up and the fixing task removes the mark.
const test = require('node:test');
const assert = require('node:assert');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const WebSocket = require('ws');

const INDEX_JS = path.join(__dirname, '..', 'index.js');
const HTTP_PORT = 8042;
const WS_PORT = 8021;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function expectedFailure(name, reason, body) {
  test(`${name} [expected failure: ${reason}]`, { timeout: 60000 }, async (t) => {
    try {
      await body(t);
    } catch (error) {
      if (!(error instanceof assert.AssertionError)) throw error;
      t.diagnostic(`fails as expected: ${error.message}`);
      return;
    }
    throw new Error(`XPASS (strict): ${reason} no longer fails; remove the expected-failure mark`);
  });
}

function portIsFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    // Loopback only: the probe must not open a port on the network. A middleware bound to every interface
    // still makes this bind fail with EADDRINUSE.
    server.listen(port, '127.0.0.1', () => server.close(() => resolve(true)));
  });
}

function freePort() {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function startMiddleware(settings) {
  for (const port of [HTTP_PORT, WS_PORT]) {
    if (!(await portIsFree(port))) throw new Error(`port ${port} is in use; stop the other middleware first`);
  }
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'kraken-node-test-'));
  fs.mkdirSync(path.join(cwd, '_share'));
  const settingsPath = path.join(cwd, '_share', 'settings.json');
  fs.writeFileSync(settingsPath, JSON.stringify(settings));
  const child = spawn(process.execPath, [INDEX_JS], { cwd, stdio: ['ignore', 'pipe', 'pipe'] });
  child.output = '';
  child.stdout.on('data', (data) => (child.output += data));
  child.stderr.on('data', (data) => (child.output += data));
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      await fetch(`http://127.0.0.1:${HTTP_PORT}/settings`);
      return { child, cwd, settingsPath };
    } catch (error) {
      await sleep(100);
    }
  }
  await stopMiddleware({ child, cwd });
  throw new Error(`middleware did not start:\n${child.output}`);
}

async function stopMiddleware({ child, cwd }) {
  if (child.exitCode === null && child.signalCode === null) {
    const exited = new Promise((resolve) => child.once('exit', resolve));
    child.kill('SIGTERM');
    await exited;
  }
  fs.rmSync(cwd, { recursive: true, force: true });
}

async function withMiddleware(settings, body) {
  const middleware = await startMiddleware(settings);
  try {
    return await body(middleware);
  } finally {
    await stopMiddleware(middleware);
  }
}

const LOCAL_SETTINGS = { center_freq: 416.588, doa_data_format: 'Kraken App', krakenpro_key: '0', station_id: 'TEST' };

function remoteSettings(mapPort) {
  return {
    center_freq: 416.588,
    doa_data_format: 'Kraken Pro Remote',
    krakenpro_key: 'TESTKEY',
    mapping_server_url: `ws://127.0.0.1:${mapPort}`,
  };
}

async function startFakeMapServer() {
  const port = await freePort();
  const server = new WebSocket.Server({ host: '127.0.0.1', port });
  server.connections = 0;
  server.on('connection', () => (server.connections += 1));
  await new Promise((resolve) => server.once('listening', resolve));
  return { server, port };
}

function closeServer(server) {
  for (const client of server.clients) client.terminate();
  return new Promise((resolve) => server.close(resolve));
}

test('GET /settings returns the settings file', { timeout: 30000 }, async () => {
  await withMiddleware(LOCAL_SETTINGS, async () => {
    const response = await fetch(`http://127.0.0.1:${HTTP_PORT}/settings`);
    assert.strictEqual(response.status, 200);
    assert.strictEqual((await response.json()).station_id, 'TEST');
  });
});

test('POST /doapost reaches a local websocket client', { timeout: 30000 }, async () => {
  await withMiddleware(LOCAL_SETTINGS, async () => {
    const client = new WebSocket(`ws://127.0.0.1:${WS_PORT}`);
    const received = [];
    client.on('message', (message) => received.push(JSON.parse(message.toString())));
    await new Promise((resolve, reject) => {
      client.once('open', resolve);
      client.once('error', reject);
    });
    const body = { freq: 416688000, radioBearing: '123', doaArray: '1,2,3,' };
    const response = await fetch(`http://127.0.0.1:${HTTP_PORT}/doapost`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    await sleep(300);
    client.close();
    assert.strictEqual(response.status, 200);
    assert.deepStrictEqual(received, [body]);
  });
});

expectedFailure('GET / serves public/index.html', 'T-22', async () => {
  await withMiddleware(LOCAL_SETTINGS, async () => {
    const response = await fetch(`http://127.0.0.1:${HTTP_PORT}/`);
    assert.strictEqual(response.status, 200);
  });
});

expectedFailure('a cross-origin POST /settings cannot overwrite the settings', 'T-20', async () => {
  await withMiddleware(LOCAL_SETTINGS, async ({ settingsPath }) => {
    await fetch(`http://127.0.0.1:${HTTP_PORT}/settings`, {
      method: 'POST',
      headers: { Origin: 'http://evil.example', 'content-type': 'application/json' },
      body: JSON.stringify({ injected: true }),
    });
    const after = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    assert.notStrictEqual(after.injected, true, `settings file is now ${JSON.stringify(after)}`);
  });
});

expectedFailure('remote mode opens exactly one connection to the map server', 'T-21, D-38', async () => {
  const map = await startFakeMapServer();
  try {
    await withMiddleware(remoteSettings(map.port), async () => {
      await sleep(2000);
      assert.strictEqual(map.server.connections, 1);
    });
  } finally {
    await closeServer(map.server);
  }
});

expectedFailure('/doapost works after a switch from remote to local mode', 'T-21, D-39', async () => {
  const map = await startFakeMapServer();
  try {
    await withMiddleware(remoteSettings(map.port), async ({ settingsPath }) => {
      await sleep(1000);
      fs.writeFileSync(settingsPath, JSON.stringify(LOCAL_SETTINGS));
      await sleep(11000); // checkForRemoteMode polls every 10 s (index.js:147,158)
      const response = await fetch(`http://127.0.0.1:${HTTP_PORT}/doapost`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ freq: 1 }),
      });
      assert.strictEqual(response.status, 200);
    });
  } finally {
    await closeServer(map.server);
  }
});

expectedFailure('an invalid message from the map server does not stop the middleware', 'D-39', async () => {
  const map = await startFakeMapServer();
  // Sent after a delay, so the middleware has finished starting before it reads the message.
  map.server.on('connection', (socket) => setTimeout(() => socket.send('this is not json'), 1500));
  try {
    await withMiddleware(remoteSettings(map.port), async ({ child }) => {
      await sleep(3000);
      assert.strictEqual(child.exitCode, null, `middleware exited:\n${child.output.slice(-500)}`);
    });
  } finally {
    await closeServer(map.server);
  }
});
