'use strict';
// Headless Chromium smoke test for the PulseDeck Web Audio UI.
// Loads the actual local HTML before touching any DOM elements.
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');
const root = path.resolve(__dirname, '..');
const htmlPath = path.join(root, 'app/src/main/assets/index.html');
const browserBin = process.env.CHROME_BIN || process.env.CHROMIUM_BIN || 'chromium';
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'pulsedeck-e2e-'));
let browser, ws, nextId = 0;
const pending = new Map();
function assert(ok, msg) { if (!ok) throw new Error(msg); }
function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
function getJson(url, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = http.request(url, { method }, res => {
      let data = ''; res.on('data', c => data += c);
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch (e) { reject(new Error(`Bad DevTools response: ${data}`)); } });
    }); req.on('error', reject); req.end();
  });
}
async function cdp(method, params = {}) {
  const id = ++nextId;
  return new Promise((resolve, reject) => { pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
}
async function evaluate(expression) {
  const r = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text || 'Browser evaluation failed');
  return r.result?.value;
}
async function waitFor(expression, timeout, label) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await evaluate(expression)) return true; await wait(100); }
  throw new Error(`Timed out waiting for ${label}`);
}
async function main() {
  assert(fs.existsSync(htmlPath), `App HTML not found: ${htmlPath}`);
  browser = spawn(browserBin, ['--headless=new', '--no-sandbox', '--disable-gpu', '--autoplay-policy=no-user-gesture-required', '--remote-debugging-port=0', `--user-data-dir=${path.join(temp, 'profile')}`, 'about:blank'], { stdio: 'ignore' });
  const portFile = path.join(temp, 'profile', 'DevToolsActivePort');
  const deadline = Date.now() + 15000;
  while (!fs.existsSync(portFile) && Date.now() < deadline) await wait(100);
  assert(fs.existsSync(portFile), `Chromium did not start. Set CHROME_BIN to a valid browser executable (tried ${browserBin}).`);
  const port = Number(fs.readFileSync(portFile, 'utf8').split(/\r?\n/)[0]);
  const target = await getJson(`http://127.0.0.1:${port}/json/new?about:blank`, 'PUT');
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  ws.onmessage = event => { const m = JSON.parse(event.data); if (!m.id || !pending.has(m.id)) return; const p = pending.get(m.id); pending.delete(m.id); if (m.error) p.reject(new Error(m.error.message)); else p.resolve(m.result); };
  // FIX: the previous test wrote to #lowA while the tab was still about:blank.
  await cdp('Page.enable');
  await cdp('Page.navigate', { url: `file://${htmlPath}` });
  await waitFor(`document.readyState === 'complete' && !!document.getElementById('lowA')`, 8000, 'PulseDeck HTML and EQ controls');
  const initial = JSON.parse(await evaluate(`JSON.stringify({lowA:!!document.getElementById('lowA'),lowB:!!document.getElementById('lowB'),playA:!!document.getElementById('playA'),playB:!!document.getElementById('playB'),diagnostics:!!window.PulseDeckDiagnostics,screenTabs:document.querySelectorAll('.screen-tab').length})`));
  assert(initial.lowA && initial.lowB, 'EQ controls for both decks did not render');
  assert(initial.playA && initial.playB, 'Both deck play controls did not render');
  await evaluate(`document.getElementById('lowA').value='-6';document.getElementById('lowA').dispatchEvent(new Event('input',{bubbles:true}))`);
  const eqValue = await evaluate(`Number(document.getElementById('lowA').value)`);
  assert(eqValue === -6, `EQ input did not retain -6 dB: ${eqValue}`);
  console.log('PulseDeck browser smoke test PASSED');
  console.log(JSON.stringify({ initial, eqValue }, null, 2));
}
main().catch(e => { console.error(`PulseDeck browser smoke test FAILED: ${e.stack || e}`); process.exitCode = 1; }).finally(() => { try { if (ws) ws.close(); } catch (_) {} try { if (browser && !browser.killed) browser.kill('SIGTERM'); } catch (_) {} try { fs.rmSync(temp, { recursive: true, force: true }); } catch (_) {} });
