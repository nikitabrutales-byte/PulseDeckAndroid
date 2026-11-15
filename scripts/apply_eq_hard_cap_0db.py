#!/usr/bin/env python3
"""Hard-cap all six PulseDeck EQ faders at 0 dB; preserve all other behavior."""
from pathlib import Path
import hashlib
import shutil
import sys

TARGET = Path("app/src/main/assets/index.html")
EXPECTED_BLOB_SHA = "a06e84de0a6664c4beb802c08640ce99b1ba32dd"

OLD_ATTR = 'type="range" min="-60" max="12" step="0.5" value="0"'
NEW_ATTR = 'type="range" min="-60" max="0" step="0.5" value="0"'
OLD_APPLY = "const control=$(`${f}${d.id}`),raw=Number(control.value),val=raw;"
NEW_APPLY = "const control=$(`${f}${d.id}`),raw=Number(control.value),val=clamp(raw,-60,0);"

def blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()

def main():
    if not TARGET.is_file():
        sys.exit(f"CHYBA: Nenalezen {TARGET}. Spusť skript v kořeni repozitáře.")
    data = TARGET.read_bytes()
    actual = blob_sha(data)
    if actual != EXPECTED_BLOB_SHA:
        sys.exit(
            "ZASTAVENO: zdrojový index.html není přesně ověřená verze.\n"
            f"Očekáváno SHA: {EXPECTED_BLOB_SHA}\n"
            f"Aktuální SHA:  {actual}\n"
            "Soubor nebyl změněn."
        )

    text = data.decode("utf-8")
    attr_count = text.count(OLD_ATTR)
    apply_count = text.count(OLD_APPLY)
    if attr_count != 6 or apply_count != 1:
        sys.exit(
            f"ZASTAVENO: očekáváno 6 EQ atributů a 1 applyDeck výraz; "
            f"nalezeno {attr_count} a {apply_count}. Soubor nebyl změněn."
        )

    updated = text.replace(OLD_ATTR, NEW_ATTR)
    updated = updated.replace(OLD_APPLY, NEW_APPLY)
    if updated.count(NEW_ATTR) != 6 or OLD_ATTR in updated or NEW_APPLY not in updated:
        sys.exit("ZASTAVENO: závěrečná kontrola neprošla. Soubor nebyl změněn.")

    backup = TARGET.with_name("index.html.before_eq_hard_cap_0db.bak")
    if backup.exists():
        sys.exit(f"ZASTAVENO: záloha už existuje: {backup}. Soubor nebyl změněn.")

    shutil.copy2(TARGET, backup)
    TARGET.write_text(updated, encoding="utf-8", newline="")
    print("HOTOVO: všech 6 EQ faderů má HTML rozsah -60 až 0 dB.")
    print("Audio engine navíc každou EQ hodnotu ořezává na -60 až 0 dB.")
    print("Hodnota 0 dB je horní doraz i výchozí hodnota.")
    print(f"Záloha: {backup}")
    print("Jiné části index.html nebyly změněny.")

if __name__ == "__main__":
    main()
