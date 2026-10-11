const fs = require('fs');
const path = require('path');

const htmlPath = path.join(__dirname, '..', 'app', 'src', 'main', 'assets', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

function extractFunction(name) {
  const marker = `function ${name}(`;
  const start = html.indexOf(marker);
  if (start < 0) throw new Error(`Missing function ${name}`);
  const open = html.indexOf('{', start);
  let depth = 0;
  for (let i = open; i < html.length; i++) {
    if (html[i] === '{') depth++;
    if (html[i] === '}') {
      depth--;
      if (depth === 0) return html.slice(start, i + 1);
    }
  }
  throw new Error(`Unclosed function ${name}`);
}

const dspFunctions = [
  extractFunction('clamp'),
  extractFunction('makeEnvelope'),
  extractFunction('estimateBpm'),
  extractFunction('refineBpm'),
  extractFunction('detectOffset'),
].join('\n');

const testBody = `
const sampleRate = 22050;
const duration = 24;
const samples = new Float32Array(sampleRate * duration);
const expectedBpm = 138;
const expectedOffset = 0.137;
const period = 60 / expectedBpm;
for (let beat = expectedOffset; beat < duration; beat += period) {
  const start = Math.floor(beat * sampleRate);
  const length = Math.floor(0.12 * sampleRate);
  for (let i = 0; i < length && start + i < samples.length; i++) {
    const t = i / sampleRate;
    samples[start + i] += Math.sin(2 * Math.PI * 55 * t) * Math.exp(-t * 32) * 0.9;
  }
}
const roughBpm = estimateBpm(samples, sampleRate);
const bpm = refineBpm(samples, sampleRate, roughBpm);
const offset = detectOffset(samples, sampleRate, bpm);
const bpmError = Math.abs(bpm - expectedBpm);
const offsetError = Math.abs(offset - expectedOffset);
console.log(JSON.stringify({ test: 'synthetic trance kick beatgrid', expectedBpm, roughBpm, bpm, expectedOffset, offset, bpmError, offsetError }));
if (bpmError > 1.5) throw new Error('BPM estimate outside 1.5 BPM tolerance');
if (offsetError > 0.06) throw new Error('First-beat offset outside 60 ms tolerance');
`;

try {
  new Function(`${dspFunctions}\n${testBody}`)();
} catch (error) {
  console.error(`DSP regression test FAILED: ${error.message}`);
  process.exit(1);
}
