#!/usr/bin/env python3
from pathlib import Path
import hashlib, shutil, sys

TARGET = Path("app/src/main/assets/index.html")
EXPECTED_BLOB_SHA = "a06e84de0a6664c4beb802c08640ce99b1ba32dd"
OLD = "const control=$(`${f}${d.id}`),raw=Number(control.value),val=raw;"
NEW = """const control=$(`${f}${d.id}`),raw=Number(control.value);
  const position=clamp((raw+60)/72,0,1),neutral=60/72;
  const val=position<=neutral
   ? -60*Math.pow((neutral-position)/neutral,2.2)
   : 12*Math.pow((position-neutral)/(1-neutral),2.2);"""

def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

def main():
    if not TARGET.is_file():
        sys.exit(f"CHYBA: Nenalezen {TARGET}. Spusť skript v kořeni repozitáře.")
    data = TARGET.read_bytes()
    actual = blob_sha(data)
    if actual != EXPECTED_BLOB_SHA:
        sys.exit(f"ZASTAVENO: nesouhlasí SHA index.html. Očekáváno {EXPECTED_BLOB_SHA}, nalezeno {actual}. Soubor nebyl změněn.")
    text = data.decode("utf-8")
    if text.count(OLD) != 1:
        sys.exit(f"ZASTAVENO: očekáván 1 výskyt cílového kódu, nalezeno {text.count(OLD)}. Soubor nebyl změněn.")
    backup = TARGET.with_name(TARGET.name + ".before_eq_curve.bak")
    if backup.exists():
        sys.exit(f"ZASTAVENO: záloha už existuje: {backup}. Soubor nebyl změněn.")
    updated = text.replace(OLD, NEW, 1)
    shutil.copy2(TARGET, backup)
    TARGET.write_text(updated, encoding="utf-8", newline="")
    print("HOTOVO: změněna pouze převodní křivka EQ HIGH/MID/LOW pro A/B.")
    print(f"Záloha: {backup}")
    print("GAIN, hlasitost desek, master, limiter, přehrávání, sync, CSS a rozložení zůstaly beze změny.")

if __name__ == "__main__":
    main()
