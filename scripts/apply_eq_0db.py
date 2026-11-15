#!/usr/bin/env python3
"""PulseDeck: hard cap the six EQ faders at 0 dB, without changing anything else."""
from pathlib import Path
import shutil
import sys

TARGET = Path("app/src/main/assets/index.html")
OLD_ATTR = 'type="range" min="-60" max="12" step="0.5" value="0"'
NEW_ATTR = 'type="range" min="-60" max="0" step="0.5" value="0"'
OLD_APPLY = "const control=$(`${f}${d.id}`),raw=Number(control.value),val=raw;"
NEW_APPLY = "const control=$(`${f}${d.id}`),raw=Number(control.value),val=Math.max(-60,Math.min(0,raw));"

def main():
    if not TARGET.is_file():
        sys.exit("CHYBA: Spusť skript v kořeni PulseDeckAndroid.")
    source = TARGET.read_text(encoding="utf-8")
    if source.count(OLD_ATTR) != 6 or source.count(OLD_APPLY) != 1:
        sys.exit("ZASTAVENO: Zdroj neodpovídá očekávané verzi (musí být 6 EQ posuvníků a 1 applyDeck). Nic nebylo změněno.")
    backup = TARGET.with_name("index.html.before_eq_0db.bak")
    if backup.exists():
        sys.exit("ZASTAVENO: Záloha už existuje: " + str(backup))
    updated = source.replace(OLD_ATTR, NEW_ATTR).replace(OLD_APPLY, NEW_APPLY)
    if updated.count(NEW_ATTR) != 6 or OLD_ATTR in updated or updated.count(NEW_APPLY) != 1:
        sys.exit("ZASTAVENO: Kontrola změny neprošla. Nic nebylo změněno.")
    shutil.copy2(TARGET, backup)
    TARGET.write_text(updated, encoding="utf-8", newline="")
    print("HOTOVO: všech 6 EQ šavlí má rozsah -60 až 0 dB.")
    print("Zvukový engine navíc odmítne každou hodnotu nad 0 dB.")
    print("Ostatní části aplikace nebyly změněny.")
    print("Záloha původního index.html: " + str(backup))

if __name__ == "__main__":
    main()
