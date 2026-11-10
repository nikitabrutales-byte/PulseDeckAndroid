#!/usr/bin/env python3
"""Apply the PulseDeck audio-engine patch to the current repository checkout.

Run from the repository root:
    python apply_pulsedeck_audio_patch.py
The script changes only app/src/main/assets/index.html and scripts/test_dsp.js.
It creates .bak backups and refuses ambiguous/already-applied edits.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "app/src/main/assets/index.html"
TEST = ROOT / "scripts/test_dsp.js"

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}. No files have been written.")
    return source.replace(old, new, 1)

def function_bounds(source: str, name: str):
    marker = f"function {name}("
    start = source.find(marker)
    if start < 0:
        raise RuntimeError(f"Function {name} was not found.")
    opening = source.find("{", start)
    if opening < 0:
        raise RuntimeError(f"Opening brace for {name} was not found.")
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    i = opening
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if line_comment:
            if ch == "\n":
                line_comment = False
        elif block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 1
        elif quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch == "/" and nxt == "/":
            line_comment = True
            i += 1
        elif ch == "/" and nxt == "*":
            block_comment = True
            i += 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    raise RuntimeError(f"Could not find the end of function {name}.")

def replace_function(source: str, name: str, replacement: str) -> str:
    start, end = function_bounds(source, name)
    return source[:start] + replacement + source[end:]

if not HTML.is_file() or not TEST.is_file():
    raise SystemExit("Spusť patch v kořenové složce repozitáře PulseDeckAndroid.")

html_original = HTML.read_text(encoding="utf-8")
test_original = TEST.read_text(encoding="utf-8")
html = html_original
test = test_original

# Lower playback latency while keeping the existing Web Audio graph and UI.
html = replace_once(
    html,
    "ctx=new(window.AudioContext||window.webkitAudioContext)({latencyHint:'playback'});",
    "ctx=new(window.AudioContext||window.webkitAudioContext)({latencyHint:'interactive'});",
    "AudioContext latency mode",
)

# If all three EQ bands are fully cut, force exact digital silence for that deck.
html = replace_once(
    html,
    "const targetGain=Math.pow(10,g/20)*vol*0.501187;",
    "const allDown=['high','mid','low'].every(k=>Number($(`${k}${d.id}`).value)<=-11.5);const targetGain=allDown?0:Math.pow(10,g/20)*vol*0.501187;",
    "Full EQ-cut mute",
)

# Start a deck at its analyzed first beat after it reaches the end.
html = replace_once(
    html,
    "let rate=1,when=ctx.currentTime,offset=(d.duration>0&&d.pos>=d.duration-.05)?0:d.pos;",
    "let rate=1,when=ctx.currentTime,offset=(d.duration>0&&d.pos>=d.duration-.05)?clamp(d.beatOffset||0,0,Math.max(0,d.duration-.02)):d.pos;",
    "Restart at first detected beat",
)

# When analysis completes while a deck is stopped, position its cue at beat one.
html = replace_once(
    html,
    "d.bpm=result.bpm;d.beatOffset=result.offset;d.analysisState='ready';",
    "d.bpm=result.bpm;d.beatOffset=result.offset;if(!d.playing)d.pos=clamp(d.beatOffset||0,0,Math.max(0,d.duration-.02));d.analysisState='ready';",
    "Initial cue at detected beat",
)

# Improve phase-lock update frequency and correction behavior without changing UI.
html = replace_function(
    html,
    "correctSync",
    """function correctSync(now){
 if(!ctx||now-lastCorrection<16)return;
 lastCorrection=now;
 const playing=Object.values(decks).filter(d=>d.playing&&d.bpm);
 if(playing.length<2)return;
 const master=masterDeck&&decks[masterDeck].playing?decks[masterDeck]:playing[0];
 const slave=playing.find(d=>d.id!==master.id);
 if(!master||!slave)return;
 const base=masterBpm/slave.bpm;
 if(base<.25||base>3)return;
 const lookahead=.015;
 const targetPhase=beatPhase(master,ctx.currentTime+lookahead);
 const slavePhase=beatPhase(slave,ctx.currentTime+lookahead);
 let err=targetPhase-slavePhase;
 if(err>.5)err-=1;
 if(err<-.5)err+=1;
 const absError=Math.abs(err);
 if(absError>.30){
  const when=ctx.currentTime+.02;
  const phase=beatPhase(master,when);
  const position=nextAlignedPosition(slave,phase,0);
  stopSource(slave);
  slave.playing=false;
  startSource(slave,when,position,base);
  $('syncState'+slave.id).textContent='FÁZE SE ZNOVU ZAMYKÁ';
  $('syncState'+slave.id).classList.add('busy');
  return;
 }
 if(absError<.008){
  if(Math.abs(base-slave.rate)>.00005)setRate(slave,base);
  $('syncState'+slave.id).textContent='AUTO BEATSYNC · ZAMČENO';
  $('syncState'+slave.id).classList.add('ok');
  return;
 }
 const gain=60/(masterBpm*.35);
 const nudge=clamp(err*gain,-.05,.05);
 const desired=clamp(base*(1+nudge),.25,3);
 if(Math.abs(desired-slave.rate)>.0001)setRate(slave,desired);
 $('syncState'+slave.id).textContent='AUTO BEATSYNC · LADĚNÍ FÁZE';
 $('syncState'+slave.id).classList.add('busy');
}""",
)

# Refine the first detected onset against the waveform instead of leaving it
# quantized to the 512-sample analysis hop.
html = replace_function(
    html,
    "detectOffset",
    """function refineOnset(samples,sr,roughTime,window=.05){
 if(roughTime<=0)return roughTime;
 const start=Math.max(0,Math.floor((roughTime-window)*sr));
 const end=Math.min(samples.length,Math.floor((roughTime+window)*sr));
 if(end<=start)return roughTime;
 let peak=0;
 for(let i=start;i<end;i+=4){const v=Math.abs(samples[i]);if(v>peak)peak=v}
 if(peak<1e-4)return roughTime;
 const threshold=peak*.1;
 for(let i=start;i<end;i++)if(Math.abs(samples[i])>threshold)return i/sr;
 return roughTime;
}
function detectOffset(samples,sr,bpm){
 const {env,hop}=makeEnvelope(samples,sr),period=60/bpm,bins=240,hist=new Float64Array(bins),onsets=[];
 for(let i=2;i<env.length-2;i++){
  const v=env[i];if(v<=0||v<env[i-1]||v<=env[i+1])continue;
  const t=i*hop/sr;onsets.push({t,v});
  const phase=((t%period)+period)%period/period;
  hist[Math.floor(phase*bins)%bins]+=v;
 }
 if(!onsets.length)return 0;
 const sm=new Float64Array(bins);
 for(let i=0;i<bins;i++)for(let d=-4;d<=4;d++)sm[i]+=hist[(i+d+bins)%bins]*(5-Math.abs(d));
 let best=0;for(let i=1;i<bins;i++)if(sm[i]>sm[best])best=i;
 let rough;
 if(!(sm[best]>0))rough=onsets[0].t;
 else{
  const phaseCenter=(best+.5)/bins,tolerance=.075;
  let earliest=null;
  for(const o of onsets){
   if(o.t>12)break;
   const phase=((o.t%period)+period)%period/period;
   const dist=Math.min(Math.abs(phase-phaseCenter),1-Math.abs(phase-phaseCenter));
   if(dist<=tolerance&&(!earliest||o.t<earliest.t))earliest=o;
  }
  rough=earliest?earliest.t:(best/bins)*period;
 }
 return refineOnset(samples,sr,rough);
}""",
)

# Make sure the worker receives the new onset-refinement helper.
html = replace_once(
    html,
    "refineBpm.toString(),detectOffset.toString(),",
    "refineBpm.toString(),refineOnset.toString(),detectOffset.toString(),",
    "Worker onset helper",
)

# Manual BeatSync must actually seek/restart an already-playing deck.
html = replace_once(
    html,
    "if(ctx&&other.playing){const phase=beatPhase(other,ctx.currentTime);d.pos=nextAlignedPosition(d,phase,.10);d.lastCtxTime=ctx.currentTime;paintDeck(d)}",
    "if(ctx&&other.playing){const when=ctx.currentTime+.02,phase=beatPhase(other,when),pos=nextAlignedPosition(d,phase,.10);if(d.playing){stopSource(d);d.playing=false;startSource(d,when,pos,rate)}else{d.pos=pos;d.lastCtxTime=ctx.currentTime;paintDeck(d)}}",
    "Manual BeatSync seek",
)

# Extend the existing regression test so the new helper is extracted as well.
test = replace_once(
    test,
    "  extractFunction('refineBpm'),\n  extractFunction('detectOffset'),",
    "  extractFunction('refineBpm'),\n  extractFunction('refineOnset'),\n  extractFunction('detectOffset'),",
    "DSP regression test helper",
)

if html == html_original or test == test_original:
    raise SystemExit("Patch neprovedl žádnou změnu; soubory zůstaly nedotčené.")

# Prepare both outputs before writing either one.
if HTML.with_suffix(HTML.suffix + ".bak").exists() or TEST.with_suffix(TEST.suffix + ".bak").exists():
    raise SystemExit("Záložní .bak soubor už existuje. Nejdřív zkontroluj předchozí patch.")

shutil.copy2(HTML, HTML.with_suffix(HTML.suffix + ".bak"))
shutil.copy2(TEST, TEST.with_suffix(TEST.suffix + ".bak"))
HTML.write_text(html, encoding="utf-8")
TEST.write_text(test, encoding="utf-8")

print("PulseDeck audio patch applied.")
print("Changed:")
print(" - app/src/main/assets/index.html")
print(" - scripts/test_dsp.js")
print("Backups:")
print(" - app/src/main/assets/index.html.bak")
print(" - scripts/test_dsp.js.bak")
print("Next: node scripts/test_dsp.js")
