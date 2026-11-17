from pathlib import Path

ROOT = Path(__file__).resolve().parent
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
     """drawWave(decks.A);
drawWave(decks.B);
requestAnimationFrame(frame);
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
     """drawWave(decks.A);
drawWave(decks.B);
requestAnimationFrame(frame);"""),
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

# Validate every anchor before writing anything, so a mismatched checkout is left untouched.
contents = {}
for path, old, new in replacements:
    if not path.is_file():
        raise SystemExit(f'MISSING FILE: {path.relative_to(REPO)}')
    contents.setdefault(path, path.read_text(encoding='utf-8'))
    if contents[path].count(old) != 1:
        raise SystemExit(f'EXPECTED ONE MATCH, FOUND {contents[path].count(old)}: {path.relative_to(REPO)}')
    contents[path] = contents[path].replace(old, new, 1)

for path, content in contents.items():
    path.write_text(content, encoding='utf-8', newline='')
    print(f'UPDATED: {path.relative_to(REPO)}')
print('Patch applied. Build and test on device before release.')
