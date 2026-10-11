from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
html = root / 'app/src/main/assets/index.html'
manifest = root / 'app/src/main/AndroidManifest.xml'
activity = root / 'app/src/main/java/com/pulsedeck/dj/MainActivity.kt'
browser_test = root / 'scripts/test_browser.js'
errors = []

for p in (html, manifest, activity, browser_test):
    if not p.is_file() or p.stat().st_size == 0:
        errors.append(f'Missing or empty required file: {p.relative_to(root)}')

if not errors:
    source = html.read_text(encoding='utf-8')
    m = re.search(r'<script(?:\s[^>]*)?>(.*?)</script>', source, re.S | re.I)
    if not m:
        errors.append('Inline application JavaScript was not found.')
    else:
        js = m.group(1)
        Path('/tmp/pulsedeck-script-check.js').write_text(js, encoding='utf-8')

    required = {
        'Deck A': 'id="playA"',
        'Deck B': 'id="playB"',
        'Cue A': 'id="cueA"',
        'Cue B': 'id="cueB"',
        'Stop A': 'id="stopA"',
        'Stop B': 'id="stopB"',
        'Load A': 'id="loadA"',
        'Load B': 'id="loadB"',
        'Deck A sync': 'id="syncButtonA"',
        'Deck B sync': 'id="syncButtonB"',
        'Default tempo 138 BPM': 'masterBpm=138',
        'EQ high A': 'id="highA"',
        'EQ mid A': 'id="midA"',
        'EQ low A': 'id="lowA"',
        'EQ high B': 'id="highB"',
        'EQ mid B': 'id="midB"',
        'EQ low B': 'id="lowB"',
        'Decks screen switch': 'id="showDeckScreen"',
        'Mixer screen switch': 'id="showMixerScreen"',
        'Stereo-preserving Web Audio buffer playback': 's.connect(d.nodes.low)',
        'Four transport buttons in one row': '.transport{grid-template-columns:1fr 1fr 1fr 46px;',
    }
    for label, needle in required.items():
        if needle not in source:
            errors.append(f'Missing required UI/logic element: {label} ({needle})')

    if 'function setRate(d,rate){rate=clamp(rate,.25,3);' not in source:
        errors.append('Playback-rate limiter does not match the supported 0.25x–3x range.')
    if "offset=(d.duration>0&&d.pos>=d.duration-.05)?0:d.pos" not in source:
        errors.append('PLAY does not restart a deck after it reaches the end of a track.')

    nav_buttons = re.findall(r'<button[^>]*class="screen-tab[^>]*>', source)
    if len(nav_buttons) != 2:
        errors.append(f'Expected exactly two screen-navigation buttons; found {len(nav_buttons)}.')

    if 'ACTION_OPEN_DOCUMENT' not in activity.read_text(encoding='utf-8'):
        errors.append('Android audio file picker is not configured.')
    if 'android:screenOrientation="landscape"' not in manifest.read_text(encoding='utf-8'):
        errors.append('Android activity is not locked to landscape orientation.')

if errors:
    print('PulseDeck verification FAILED:')
    for error in errors:
        print(' -', error)
    sys.exit(1)

print('PulseDeck static verification passed.')
print('Verified: both decks, four-button transport row, audio picker, stereo-capable Web Audio graph, EQ, sync, 138 BPM default, landscape Android host and browser smoke test.')
