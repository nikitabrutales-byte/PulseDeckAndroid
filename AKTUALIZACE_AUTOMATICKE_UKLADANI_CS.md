# PulseDeck – automatická příprava trvalé složky

## Změna
- Při prvním načtení aplikace se automaticky otevře systémový výběr umístění Androidu.
- Po potvrzení umístění aplikace vytvoří `PulseDeck/` a podsložky `Library/Tracks`, `Analysis`, `Playlists`, `Mix Projects`, `Recordings`, `Library Backup` a `Backup`.
- Zvolený přístup se uloží přes Storage Access Framework a při dalších spuštěních se znovu použije.
- Pokud uživatel výběr zruší, aplikace zůstane použitelná a výběr lze znovu otevřít v kartě knihovny.

## Omezení Androidu
Android nedovoluje aplikaci potichu vytvořit veřejnou složku bez souhlasu uživatele. Jednorázové potvrzení v systémovém dialogu je povinné.

## Ověření
- `python3 scripts/verify_pulsedeck.py` – prošlo.
- `node scripts/test_dsp.js` – prošlo; detekce testovacího tempa 137.99 BPM.
- `node scripts/test_browser.js` – neprošlo; test čekal na HTML/EQ ovládací prvky a vypršel časový limit.
- Android APK nebylo možné sestavit v tomto prostředí (není dostupný Gradle/Android SDK).
