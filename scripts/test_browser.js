'use strict';
// End-to-end Web Audio smoke test. Requires Chromium/Chrome and Node 18+.
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');

const root = path.resolve(__dirname, '..');
const htmlPath = path.join(root, 'app/src/main/assets/index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const browserBin = process.env.CHROME_BIN || process.env.CHROMIUM_BIN || 'chromium';
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'pulsedeck-e2e-'));
let browser;
let ws;
let nextId = 0;
const pending = new Map();

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function wait(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function makeStereoWav(filePath, seconds = 12, sampleRate = 22050, bpm = 138, offset = 0.137) {
  const channels = 2, bits = 16, dataBytes = seconds * sampleRate * channels * 2;
  const out = Buffer.alloc(44 + dataBytes);
  out.write('RIFF', 0); out.writeUInt32LE(36 + dataBytes, 4); out.write('WAVE', 8);
  out.write('fmt ', 12); out.writeUInt32LE(16, 16); out.writeUInt16LE(1, 20);
  out.writeUInt16LE(channels, 22); out.writeUInt32LE(sampleRate, 24);
  out.writeUInt32LE(sampleRate * channels * 2, 28); out.writeUInt16LE(channels * 2, 32);
  out.writeUInt16LE(bits, 34); out.write('data', 36); out.writeUInt32LE(dataBytes, 40);
  const beatPeriod = 60 / bpm;
  for (let i = 0; i < seconds * sampleRate; i++) {
    const t = i / sampleRate;
    const beatNo = Math.max(0, Math.floor((t - offset) / beatPeriod));
    const dt = t - (offset + beatNo * beatPeriod);
    const kick = dt >= 0 && dt < 0.14 ? 0.58 * Math.sin(2 * Math.PI * (58 - 110 * dt) * dt) * Math.exp(-dt * 25) : 0;
    const left = Math.max(-1, Math.min(1, kick + 0.035 * Math.sin(2 * Math.PI * 440 * t)));
    const right = Math.max(-1, Math.min(1, kick + 0.035 * Math.sin(2 * Math.PI * 660 * t)));
    const at = 44 + i * 4;
    out.writeInt16LE(Math.round(left * 32767), at);
    out.writeInt16LE(Math.round(right * 32767), at + 2);
  }
  fs.writeFileSync(filePath, out);
}
function getJson(url, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = http.request(url, { method }, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (err) { reject(new Error(`Bad DevTools response: ${data}`)); }
      });
    });
    req.on('error', reject); req.end();
  });
}
async function cdp(method, params = {}) {
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const response = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text || 'Browser evaluation failed');
  }
  return response.result?.value;
}
async function waitFor(expression, timeoutMs, label) {
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    const value = await evaluate(expression);
    if (value) return value;
    await wait(150);
  }
  throw new Error(`Timed out waiting for ${label}`);
}
async function main() {
  const wavPath = path.join(temp, 'synthetic-trance-138bpm-stereo.wav');
  makeStereoWav(wavPath);
  browser = spawn(browserBin, [
    '--headless=new', '--no-sandbox', '--disable-gpu', '--autoplay-policy=no-user-gesture-required',
    '--remote-debugging-port=0', `--user-data-dir=${path.join(temp, 'profile')}`, 'about:blank'
  ], { stdio: 'ignore' });
  const portFile = path.join(temp, 'profile', 'DevToolsActivePort');
  const deadline = Date.now() + 15000;
  while (!fs.existsSync(portFile) && Date.now() < deadline) await wait(100);
  assert(fs.existsSync(portFile), `Chromium did not start. Set CHROME_BIN to a valid browser executable (tried ${browserBin}).`);
  const port = Number(fs.readFileSync(portFile, 'utf8').split(/\r?\n/)[0]);
  const target = await getJson(`http://127.0.0.1:${port}/json/new?about:blank`, 'PUT');
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  ws.onmessage = event => {
    const msg = JSON.parse(event.data);
    if (!msg.id || !pending.has(msg.id)) return;
    const entry = pending.get(msg.id); pending.delete(msg.id);
    if (msg.error) entry.reject(new Error(msg.error.message)); else entry.resolve(msg.result);
  };
  await evaluate(`document.open();document.write(${JSON.stringify(html)});document.close();true`);
  await waitFor(`document.readyState === 'complete' && !!window.PulseDeckDiagnostics`, 5000, 'app initialization');
  const initial = JSON.parse(await evaluate(`JSON.stringify({decks:!!document.getElementById('playA')&&!!document.getElementById('playB'),tabs:document.querySelectorAll('.screen-tab').length,transportColumns:getComputedStyle(document.querySelector('#deckA .transport')).gridTemplateColumns})`));
  assert(initial.decks, 'Both decks did not render');
  assert(initial.tabs === 2, `Expected 2 screen tabs, got ${initial.tabs}`);
  assert(initial.transportColumns.split(' ').length === 4, `Expected PLAY/CUE/STOP/load in one row, got columns ${initial.transportColumns}`);

  const dom = await cdp('DOM.getDocument');
  const fileNodeA = await cdp('DOM.querySelector', { nodeId: dom.root.nodeId, selector: '#fileA' });
  await cdp('DOM.setFileInputFiles', { files: [wavPath], nodeId: fileNodeA.nodeId });
  await waitFor(`PulseDeckDiagnostics.state.bpm.A > 130`, 15000, 'Deck A BPM analysis');
  const loadedA = JSON.parse(await evaluate(`JSON.stringify({channels:decks.A.buffer.numberOfChannels,bpm:decks.A.bpm,offset:decks.A.beatOffset,duration:decks.A.duration})`));
  assert(loadedA.channels === 2, `Stereo file decoded as ${loadedA.channels} channels`);
  assert(Math.abs(loadedA.bpm - 138) < 1.5, `BPM analysis failed: ${loadedA.bpm}`);
  assert(Math.abs(loadedA.offset - 0.137) < 0.07, `Beat offset analysis failed: ${loadedA.offset}`);

  await evaluate(`document.getElementById('playA').click()`);
  await waitFor(`PulseDeckDiagnostics.state.playing.A === true`, 3000, 'Deck A playback');
  await waitFor(`typeof ctx !== 'undefined' && ctx && ctx.state === 'running'`, 3000, 'Web Audio context');
  await evaluate(`document.getElementById('lowA').value='6';document.getElementById('lowA').dispatchEvent(new Event('input',{bubbles:true}))`);
  await wait(100);
  const eqGain = await evaluate(`decks.A.nodes.low.gain.value`);
  assert(Math.abs(eqGain - 6) < 0.1, `Low EQ did not apply: ${eqGain} dB`);

  const domAfter = await cdp('DOM.getDocument');
  const fileNodeB = await cdp('DOM.querySelector', { nodeId: domAfter.root.nodeId, selector: '#fileB' });
  await cdp('DOM.setFileInputFiles', { files: [wavPath], nodeId: fileNodeB.nodeId });
  await waitFor(`PulseDeckDiagnostics.state.bpm.B > 130`, 15000, 'Deck B BPM analysis');
  await evaluate(`document.getElementById('syncButtonB').click()`);
  await waitFor(`PulseDeckDiagnostics.state.playing.B === true`, 3000, 'Deck B sync playback');
  const synced = JSON.parse(await evaluate(`JSON.stringify({playing:PulseDeckDiagnostics.state.playing,bpm:PulseDeckDiagnostics.state.bpm,channelsA:decks.A.buffer.numberOfChannels,channelsB:decks.B.buffer.numberOfChannels,nodeChannelsA:[decks.A.nodes.low.channelCount,decks.A.nodes.mid.channelCount,decks.A.nodes.high.channelCount],nodeChannelsB:[decks.B.nodes.low.channelCount,decks.B.nodes.mid.channelCount,decks.B.nodes.high.channelCount],eq:decks.A.nodes.low.gain.value,ctx:ctx.state})`));
  assert(synced.playing.A && synced.playing.B, 'Both decks are not playing after sync');
  assert(synced.channelsA === 2 && synced.channelsB === 2, 'Stereo was not preserved for both decks');
  assert(synced.nodeChannelsA.every(n => n === 2) && synced.nodeChannelsB.every(n => n === 2), 'One of the EQ filter nodes is not configured for stereo');
  await evaluate(`document.getElementById('showMixerScreen').click()`);
  assert(await evaluate(`document.getElementById('mixerScreen').hidden === false && document.getElementById('deckScreen').hidden === true`), 'Mixer screen switch failed');
  await evaluate(`document.getElementById('showDeckScreen').click()`);
  assert(await evaluate(`document.getElementById('deckScreen').hidden === false && document.getElementById('mixerScreen').hidden === true`), 'Deck screen switch failed');

  console.log('PulseDeck browser smoke test PASSED');
  console.log(JSON.stringify({ initial, loadedA, synced, eqGain }, null, 2));
}
main().catch(error => { console.error(`PulseDeck browser smoke test FAILED: ${error.stack || error}`); process.exitCode = 1; }).finally(() => {
  try { if (ws) ws.close(); } catch (_) {}
  try { if (browser && !browser.killed) browser.kill('SIGTERM'); } catch (_) {}
  try { fs.rmSync(temp, { recursive: true, force: true }); } catch (_) {}
});
