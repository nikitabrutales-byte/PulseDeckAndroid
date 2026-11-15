#!/usr/bin/env python3
"""Cap all six PulseDeck EQ controls at 0 dB and use full travel for attenuation."""
from pathlib import Path
import hashlib
import shutil
import sys

TARGET = Path("app/src/main/assets/index.html")
EXPECTED_BLOB_SHA = "a06e84de0a6664c4beb802c08640ce99b1ba32dd"

OLD_A = 'type="range" min="-60" max="12" step="0.5" value="0"'
NEW_A = 'type="range" min="-60" max="0" step="0.5" value="0"'

def blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()

def main() -> None:
    if not TARGET.is_file():
        sys.exit(f"CHYBA: Nenalezen {TARGET}. Spusť skript v kořeni repozitáře.")

    data = TARGET.read_bytes()
    actual = blob_sha(data)
    if actual != EXPECTED_BLOB_SHA:
        sys.exit(
            "ZASTAVENO: index.html neodpovídá ověřené verzi.\n"
            f"Očekáváno: {EXPECTED_BLOB_SHA}\n"
            f"Nalezeno:  {actual}\n"
            "Soubor nebyl změněn."
        )

    text = data.decode("utf-8")
    count = text.count(OLD_A)
    if count != 6:
        sys.exit(
            f"ZASTAVENO: očekáváno přesně 6 EQ ovladačů, nalezeno {count}. "
            "Soubor nebyl změněn."
        )

    backup = TARGET.with_name(TARGET.name + ".before_eq_zero_cap.bak")
    if backup.exists():
        sys.exit(f"ZASTAVENO: záloha už existuje: {backup}. Soubor nebyl změněn.")

    updated = text.replace(OLD_A, NEW_A)
    if updated.count(NEW_A) != 6 or updated.count(OLD_A) != 0:
        sys.exit("ZASTAVENO: kontrola výsledku neprošla. Soubor nebyl změněn.")

    shutil.copy2(TARGET, backup)
    TARGET.write_text(updated, encoding="utf-8", newline="")
    print("HOTOVO: všech 6 EQ ovladačů má rozsah −60 až 0 dB.")
    print("Výchozí hodnota 0 dB je na horním dorazu.")
    print(f"Záloha: {backup}")
    print("Změněno pouze šest HTML rozsahů EQ. Funkce applyDeck ani ostatní části nebyly změněny.")

if __name__ == "__main__":
    main()
