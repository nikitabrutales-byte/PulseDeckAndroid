#!/usr/bin/env python3
"""Apply a guarded audio-engine-only patch to PulseDeckAndroid."""
from pathlib import Path
import hashlib
import sys

EXPECTED_INDEX_BLOB_SHA = "31a5ddc10995430696928fbe9ba798a5017d1f79"

def find_repo_root():
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / "app/src/main/assets/index.html").is_file():
            return candidate
    raise SystemExit("ERROR: Run this script from inside the PulseDeckAndroid repository.")

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"STOP: '{label}' expected exactly once, found {count}. No files were changed.")
    return source.replace(old, new, 1)

def function_bounds(source: str, name: str):
    marker = f"function {name}("
    start = source.find(marker)
    if start < 0:
        raise SystemExit(f"STOP: Function {name} was not found. No files were changed.")
    open_brace = source.find("{", start)
    if open_brace < 0:
        raise SystemExit(f"STOP: Function {name} has no body.")
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    i = open_brace
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
    raise SystemExit(f"STOP: Could not find the end of function {name}.")

def replace_function(source: str, name: str, replacement: str) -> str:
    start, end = function_bounds(source, name)
    return source[:start] + replacement + source[end:]

def main():
    root = find_repo_root()
    index_path = root / "app/src/main/assets/index.html"
    test_path = root / "scripts/test_dsp.js"

    original_bytes = index_path.read_bytes()
    actual_sha = git_blob_sha(original_bytes)
    if actual_sha != EXPECTED_INDEX_BLOB_SHA:
        raise SystemExit(
            "STOP: index.html is not the exact source version this patch was prepared for.\n"
            f"Expected Git blob SHA: {EXPECTED_INDEX_BLOB_SHA}\n"
            f"Found Git blob SHA:    {actual_sha}\n"
            "No files were changed. Upload your current index.html so the patch can be adapted safely."
        )

    source = original_bytes.decode("utf-8")

    patches = [
        ("AudioContext low-latency mode",
         "ctx=new(window.AudioContext||window.webkitAudioContext)({latencyHint:'playback'});",
         "ctx=new(window.AudioContext||window.webkitAudioContext)({latencyHint:'interactive'});"),
        ("Master limiter profile",
         "limiter.threshold.value=-6;limiter.knee.value=6;limiter.ratio.value=16;limiter.attack.value=0.008;limiter.release.value=0.24;",
         "limiter.threshold.value=-3;limiter.knee.value=0;limiter.ratio.value=20;limiter.attack.value=0.003;limiter.release.value=0.12;"),
        ("Audio warm-up before click",
         "document.addEventListener('pointerdown',warmAudioEngine,{once:true,passive:true});",
         "document.addEventListener('pointerdown',warmAudioEngine,{capture:true,passive:true});"),
        ("Hard mute when all EQ bands are fully cut",
         "const targetGain=Math.pow(10,g/20)*vol*0.501187;",
         "const allDown=['high','mid','low'].every(k=>Number($(`${k}${d.id}`).value)<=-11.5);const targetGain=allDown?0:Math.pow(10,g/20)*vol*0.501187;"),
        ("playDeck returns a promise without awaiting",
         "function playDeck(id){",
         "async function playDeck(id){"),
        ("Restart at first detected beat",
         "let rate=1,when=ctx.currentTime,offset=(d.duration>0&&d.pos>=d.duration-.05)?0:d.pos;",
         "let rate=1,when=ctx.currentTime,offset=(d.duration>0&&d.pos>=d.duration-.05)?clamp(d.beatOffset||0,0,Math.max(0,d.duration-.02)):d.pos;"),
        ("Set initial cue to detected first beat",
         "d.bpm=result.bpm;d.beatOffset=result.offset;d.analysisState='ready';",
         "d.bpm=result.bpm;d.beatOffset=result.offset;if(!d.playing)d.pos=clamp(d.beatOffset||0,0,Math.max(0,d.duration-.02));d.analysisState='ready';"),
        ("Worker includes onset refinement",
         "refineBpm.toString(),detectOffset.toString(),",
         "refineBpm.toString(),refineOnset.toString(),detectOffset.toString(),"),
        ("Worker fallback analysis",
         "  const fallback=()=>{\n   // Keep expensive beat analysis off the UI thread.\n   // If Workers are unavailable, leave BPM unset instead of freezing playback.\n   resolve({bpm:0,offset:0,analysisUnavailable:true});\n  };",
         "  const fallback=()=>{\n   try{const rough=estimateBpm(samples,sampleRate);if(!rough){resolve({bpm:0,offset:0,analysisUnavailable:true});return;}const bpm=refineBpm(samples,sampleRate,rough);const offset=detectOffset(samples,sampleRate,bpm);resolve({bpm,offset});}\n   catch(_){resolve({bpm:0,offset:0,analysisUnavailable:true});}\n  };"),
        ("Worker creation fallback",
         "  }catch(_){finish({bpm:0,offset:0})}",
         "  }catch(_){fallback()}"),
        ("Manual sync actually seeks a playing deck",
         "if(ctx&&other.playing){const phase=beatPhase(other,ctx.currentTime);d.pos=nextAlignedPosition(d,phase,.10);d.lastCtxTime=ctx.currentTime;paintDeck(d)}",
         "if(ctx&&other.playing){const when=ctx.currentTime+.02,phase=beatPhase(other,when),pos=nextAlignedPosition(d,phase,.10);if(d.playing){stopSource(d);d.playing=false;startSource(d,when,pos,rate)}else{d.pos=pos;d.lastCtxTime=ctx.currentTime;paintDeck(d)}}"),
    ]
    for label, old, new in patches:
        source = replace_once(source, old, new, label)

    source = replace_function(
        source, "setRate",
        "function setRate(d,rate,instant=false){rate=clamp(rate,.25,3);if(d.playing&&ctx&&d.source){if(ctx.currentTime>=d.lastCtxTime){updatePosition(d);d.lastCtxTime=ctx.currentTime}const delta=Math.abs(rate-d.rate);d.rate=rate;try{const t=Math.max(ctx.currentTime,d.lastCtxTime);if(instant||delta<.004)d.source.playbackRate.setValueAtTime(rate,t);else d.source.playbackRate.setTargetAtTime(rate,t,.05)}catch(_){d.source.playbackRate.value=rate}}else d.rate=rate;}"
    )
    source = replace_function(
        source, "correctSync",
        "function correctSync(){if(!ctx)return;const nowMs=performance.now();if(nowMs-lastCorrection<16)return;lastCorrection=nowMs;const playing=Object.values(decks).filter(d=>d.playing&&d.bpm);if(playing.length<2)return;const master=masterDeck&&decks[masterDeck].playing?decks[masterDeck]:playing[0];const slave=playing.find(d=>d.id!==master.id);if(!master||!master.playing||!slave)return;const base=masterBpm/slave.bpm;if(base<.25||base>3)return;const lookahead=.01;const targetPhase=beatPhase(master,ctx.currentTime+lookahead);const slavePhase=beatPhase(slave,ctx.currentTime+lookahead);let err=targetPhase-slavePhase;if(err>.5)err-=1;if(err<-.5)err+=1;const absError=Math.abs(err);if(absError>.3){const when=ctx.currentTime+.02;const phase=beatPhase(master,when);const position=nextAlignedPosition(slave,phase,0);stopSource(slave);slave.playing=false;startSource(slave,when,position,base);$('syncState'+slave.id).textContent='FÁZE SE ZNOVU ZAMYKÁ';$('syncState'+slave.id).classList.add('busy');return}if(absError<.008){if(Math.abs(base-slave.rate)>.00005)setRate(slave,base,true);$('syncState'+slave.id).textContent='AUTO BEATSYNC · ZAMČENO';$('syncState'+slave.id).classList.add('ok');return}const gain=60/(masterBpm*.35);const nudge=clamp(err*gain,-.05,.05);const desired=clamp(base*(1+nudge),.25,3);if(Math.abs(desired-slave.rate)>.0001)setRate(slave,desired,true);$('syncState'+slave.id).textContent='AUTO BEATSYNC · LADĚNÍ FÁZE';$('syncState'+slave.id).classList.add('busy')}"
    )
    source = replace_function(
        source, "detectOffset",
        "function refineOnset(samples,sr,roughTime,window=.05){if(roughTime<=0)return roughTime;const start=Math.max(0,Math.floor((roughTime-window)*sr)),end=Math.min(samples.length,Math.floor((roughTime+window)*sr));if(end<=start)return roughTime;let peak=0;for(let i=start;i<end;i+=4){const v=Math.abs(samples[i]);if(v>peak)peak=v}if(peak<1e-4)return roughTime;const threshold=peak*.1;for(let i=start;i<end;i++){if(Math.abs(samples[i])>threshold)return i/sr}return roughTime}\n function detectOffset(samples,sr,bpm){const {env,hop}=makeEnvelope(samples,sr),period=60/bpm,bins=240,hist=new Float64Array(bins),onsets=[];for(let i=2;i<env.length-2;i++){const v=env[i];if(v<=0||v<env[i-1]||v<=env[i+1])continue;const t=i*hop/sr;onsets.push({t,v});const phase=((t%period)+period)%period/period;hist[Math.floor(phase*bins)%bins]+=v}if(!onsets.length)return 0;const sm=new Float64Array(bins);for(let i=0;i<bins;i++)for(let d=-4;d<=4;d++)sm[i]+=hist[(i+d+bins)%bins]*(5-Math.abs(d));let best=0;for(let i=1;i<bins;i++)if(sm[i]>sm[best])best=i;let rough;if(!(sm[best]>0)){rough=onsets[0].t}else{const phaseCenter=(best+.5)/bins,tolerance=.075;let earliest=null;for(const o of onsets){if(o.t>12)break;const phase=((o.t%period)+period)%period/period;const dist=Math.min(Math.abs(phase-phaseCenter),1-Math.abs(phase-phaseCenter));if(dist<=tolerance&&(!earliest||o.t<earliest.t))earliest=o}rough=earliest?earliest.t:(best/bins)*period}return refineOnset(samples,sr,rough)}"
    )

    test_source = test_path.read_text(encoding="utf-8")
    test_source = replace_once(
        test_source,
        "  extractFunction('refineBpm'),\n  extractFunction('detectOffset'),",
        "  extractFunction('refineBpm'),\n  extractFunction('refineOnset'),\n  extractFunction('detectOffset'),",
        "DSP regression test includes onset refinement"
    )

    # Preserve exact originals before writing either file.
    index_backup = index_path.with_name("index.html.before_audio_engine_parity.bak")
    test_backup = test_path.with_name("test_dsp.js.before_audio_engine_parity.bak")
    if index_backup.exists() or test_backup.exists():
        raise SystemExit("STOP: A previous audio-engine backup already exists. Move it aside before applying this patch.")
    index_backup.write_bytes(original_bytes)
    test_backup.write_text(test_path.read_text(encoding="utf-8"), encoding="utf-8")
    index_path.write_text(source, encoding="utf-8")
    test_path.write_text(test_source, encoding="utf-8")

    print("PulseDeck audio-engine patch applied.")
    print("Changed only:")
    print(" - app/src/main/assets/index.html (JavaScript audio engine only; HTML/CSS/layout untouched)")
    print(" - scripts/test_dsp.js (test now includes onset refinement)")
    print("Backups:")
    print(" - app/src/main/assets/index.html.before_audio_engine_parity.bak")
    print(" - scripts/test_dsp.js.before_audio_engine_parity.bak")
    print("Next: python scripts/verify_pulsedeck.py && node --check /tmp/pulsedeck-script-check.js && node scripts/test_dsp.js")

if __name__ == "__main__":
    main()
