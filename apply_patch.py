from pathlib import Path
import re, subprocess, sys, tempfile

REPO = Path.cwd()
HTML = REPO / 'app/src/main/assets/index.html'
KOTLIN = REPO / 'app/src/main/java/com/pulsedeck/dj/MainActivity.kt'
replacements = [
    (HTML,
     """// Warm the audio engine on the user's first real interaction, before PLAY is pressed.
function warmAudioEngine(){try{ensureEngine().catch(()=>{});}catch(_){}}
document.addEventListener('pointerdown',warmAudioEngine,{once:true,passive:true});
document.addEventListener('touchstart',warmAudioEngine,{once:true,passive:true});
document.addEventListener('keydown',warmAudioEngine,{once:true});""",
     """// Start/resume the audio engine on pointer-down, before the PLAY click handler runs.
let engineResumePromise=null;
function warmAudioEngine(){
 if(ctx&&ctx.state==='running')return Promise.resolve(ctx);
 if(engineResumePromise)return engineResumePromise;
 try{
  const pending=ensureEngine();
  engineResumePromise=pending;
  pending.finally(()=>{if(engineResumePromise===pending)engineResumePromise=null;}).catch(()=>{});
  return pending;
 }catch(error){console.error('Audio engine warm-up failed:',error);return Promise.reject(error)}
}
document.addEventListener('pointerdown',warmAudioEngine,{capture:true,passive:true});
document.addEventListener('touchstart',warmAudioEngine,{capture:true,passive:true});
document.addEventListener('keydown',warmAudioEngine,{capture:true});"""),
    (HTML,
     """async function playDeck(id){const d=decks[id];if(!d.buffer){msg('Nejdřív načti skladbu do Deck '+id+'.');return}if(d.playing){stopDeck(d,false);return}if(!ctx||ctx.state!=='running')await ensureEngine();else if(!d.nodes)buildNodes(d);""",
     """async function playDeck(id){const d=decks[id];if(!d.buffer){msg('Nejdřív načti skladbu do Deck '+id+'.');return}if(d.playing){stopDeck(d,false);return}if(!ctx||ctx.state!=='running')await (engineResumePromise||warmAudioEngine());else if(!d.nodes)buildNodes(d);"""),
    (HTML,
     """requestAnimationFrame(frame);
  if(document.hidden){
 if(frameRequest){cancelAnimationFrame(frameRequest);frameRequest=0;}
  return;
 }
 if(ctx&&ctx.state==='suspended'){
  ctx.resume().then(()=>scheduleFrame()).catch(e=>console.error('Audio resume failed:',e));
 }else{
  scheduleFrame();
 }
});()});drawWave(decks.A);drawWave(decks.B);requestAnimationFrame(frame);""",
     """requestAnimationFrame(frame);"""),
    (KOTLIN,
     """        override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_USER
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)""",
     """    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_USER)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)"""),
]
originals={}
updated={}
for path, old, new in replacements:
    if not path.is_file(): raise SystemExit(f'MISSING FILE: {path.relative_to(REPO)}')
    originals.setdefault(path,path.read_text(encoding='utf-8'))
    updated.setdefault(path,originals[path])
    count=updated[path].count(old)
    if count != 1: raise SystemExit(f'EXPECTED ONE MATCH, FOUND {count}: {path.relative_to(REPO)}')
    updated[path]=updated[path].replace(old,new,1)

# Validate the resulting JavaScript before touching the checkout.
html=updated[HTML]
blocks=re.findall(r'<script\b[^>]*>(.*?)</script\s*>',html,re.I|re.S)
if len(blocks) != 1: raise SystemExit(f'EXPECTED ONE SCRIPT BLOCK, FOUND {len(blocks)}')
with tempfile.NamedTemporaryFile('w',suffix='.js',encoding='utf-8',delete=False) as f:
    f.write(blocks[0]); js_path=Path(f.name)
try:
    check=subprocess.run(['node','--check',str(js_path)],capture_output=True,text=True)
finally:
    js_path.unlink(missing_ok=True)
if check.returncode:
    sys.stderr.write(check.stderr)
    raise SystemExit('JavaScript syntax check failed; checkout left unchanged.')

for path,content in updated.items(): path.write_text(content,encoding='utf-8',newline='')
print('UPDATED: app/src/main/assets/index.html')
print('UPDATED: app/src/main/java/com/pulsedeck/dj/MainActivity.kt')
print('PASS: node --check on embedded JavaScript')
print('Now rerun GitHub Actions and test audio on device.')
