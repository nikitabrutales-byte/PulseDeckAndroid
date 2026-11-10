#!/usr/bin/env python3
from pathlib import Path
import shutil, sys

target = Path("app/src/main/assets/index.html")
if not target.is_file():
    sys.exit("CHYBA: Spusť skript v kořenové složce PulseDeckAndroid.")
s = target.read_text(encoding="utf-8")
old1 = "new(window.AudioContext||window.webkitAudioContext)({latencyHint:'playback'})"
new1 = "new(window.AudioContext||window.webkitAudioContext)({latencyHint:'interactive'})"
old2 = "document.addEventListener('pointerdown',warmAudioEngine,{once:true,passive:true});"
new2 = ("document.addEventListener('pointerdown',warmAudioEngine,{capture:true,passive:true});\n"
        "document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')warmAudioEngine()});")
if s.count(old1) != 1 or s.count(old2) != 1:
    sys.exit("CHYBA: Zdrojový index.html neodpovídá očekávané verzi. Nebyl změněn.")
backup = target.with_name("index.html.before_bluetooth_latency_fix.bak")
if backup.exists():
    sys.exit("CHYBA: Záloha už existuje; přejmenuj ji nebo ověř předchozí úpravu.")
shutil.copy2(target, backup)
updated = s.replace(old1, new1).replace(old2, new2)
target.write_text(updated, encoding="utf-8")
print("Hotovo. Záloha:", backup)
print("AudioContext je nyní interactive; audio se zahřívá při každém dotyku a po návratu do aplikace.")
