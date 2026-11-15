#!/usr/bin/env python3
"""Apply only the Traktor-inspired gentle channel-volume fader curve to PulseDeck."""
from pathlib import Path
import hashlib
import shutil
import sys

TARGET = Path("app/src/main/assets/index.html")
EXPECTED_BLOB_SHA = "a06e84de0a6664c4beb802c08640ce99b1ba32dd"

OLD = "function smoothVolumeCurve(raw){return clamp(Number(raw)/100,0,1)}"
NEW = "function smoothVolumeCurve(raw){const position=clamp(Number(raw)/100,0,1);return Math.sin(position*Math.PI/2)}"

def git_blob_sha(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()

def main():
    if not TARGET.is_file():
        sys.exit(f"CHYBA: Nenalezen {TARGET}. Spusť skript v kořeni repozitáře.")
    data = TARGET.read_bytes()
    actual = git_blob_sha(data)
    if actual != EXPECTED_BLOB_SHA:
        sys.exit(
            "ZASTAVENO: index.html neodpovídá ověřené verzi.\n"
            f"Očekávaný blob SHA: {EXPECTED_BLOB_SHA}\n"
            f"Aktuální blob SHA:  {actual}\n"
            "Soubor nebyl změněn. Nejdřív je nutné patch přizpůsobit aktuálnímu zdroji."
        )
    text = data.decode("utf-8")
    if text.count(OLD) != 1:
        sys.exit(f"ZASTAVENO: očekával jsem přesně 1 výskyt funkce, nalezeno {text.count(OLD)}. Soubor nebyl změněn.")
    backup = TARGET.with_name(TARGET.name + ".before_channel_fader_curve.bak")
    if backup.exists():
        sys.exit(f"ZASTAVENO: záloha už existuje: {backup}. Soubor nebyl změněn.")
    shutil.copy2(TARGET, backup)
    updated = text.replace(OLD, NEW, 1)
    TARGET.write_text(updated, encoding="utf-8", newline="")
    print("HOTOVO: upravena pouze funkce smoothVolumeCurve() v index.html.")
    print(f"Záloha: {backup}")
    print("Ostatní soubory a funkce nebyly změněny.")

if __name__ == "__main__":
    main()
