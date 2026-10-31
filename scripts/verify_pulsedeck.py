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
        Path('/tmp/pulsedeck-script-check.js').write_text(m.group(1), encoding='utf-8')

    required = {
        'Deck A': 'id="playA"', 'Deck B': 'id="playB"',
        'Cue A': 'id="cueA"', 'Cue B': 'id="cueB"',
        'Stop A': 'id="stopA"', 'Stop B': 'id="stopB"',
        'Load A': 'id="loadA"', 'Load B': 'id="loadB"',
        'Deck A sync': 'id="syncButtonA"', 'Deck B sync': 'id="syncButtonB"',
        'Default tempo 138 BPM': 'masterBpm=138',
        'EQ high A': 'id="highA"', 'EQ mid A': 'id="midA"', 'EQ low A': 'id="lowA"',
        'EQ high B': 'id="highB"', 'EQ mid B': 'id="midB"', 'EQ low B': 'id="lowB"',
        'Decks screen switch': 'id="showDeckScreen"',
        'Mixer screen switch': 'id="showMixerScreen"',
        'Library screen switch': 'id="showLibraryScreen"',
        'Recording screen switch': 'id="showRecordingScreen"',
        'Folder picker button': 'id="libraryFolderNative"',
        'Folder picker JS bridge': 'window.PulseDeckAndroid.openFolderPicker()',
        'Native folder scan callback': 'window.onNativeFolderPicked=onNativeFolderPicked',
        'Native chunked audio reader': 'readAudioFileChunk',
        'Stereo-preserving Web Audio buffer playback': 's.connect(d.nodes.low)',
        'Traktor-style horizontal fader thumb': 'width:42px!important;height:14px!important',
    }
    for label, needle in required.items():
        if needle not in source:
            errors.append(f'Missing required UI/logic element: {label} ({needle})')

    nav_buttons = re.findall(r'<button[^>]*class="screen-tab[^>]*>(.*?)</button>', source, re.S)
    nav_labels = [re.sub(r'<[^>]+>', '', label).strip() for label in nav_buttons]
    expected_nav = ['DESKY', 'MIXER', 'KNIHOVNA', 'LOCAL MIX RECORDING']
    if nav_labels != expected_nav:
        errors.append(f'Expected four navigation tabs in order {expected_nav}; found {nav_labels}.')

    native = activity.read_text(encoding='utf-8')
    for label, needle in {
        'SAF folder picker': 'Intent.ACTION_OPEN_DOCUMENT_TREE',
        'JavaScript bridge': 'addJavascriptInterface(PulseDeckFolderBridge(), "PulseDeckAndroid")',
        'Recursive folder scan': 'appendAudioFiles(tree, rootId',
        'Chunked audio reading': 'fun readAudioFileChunk',
        'Persisted folder permission': 'takePersistableUriPermission',
        'Multiple file selection': 'Intent.EXTRA_ALLOW_MULTIPLE, true',
    }.items():
        if needle not in native:
            errors.append(f'Missing Android folder/file feature: {label} ({needle})')

    if 'ACTION_OPEN_DOCUMENT' not in native:
        errors.append('Android audio file picker is not configured.')
    if 'android:screenOrientation="fullSensor"' not in manifest.read_text(encoding='utf-8'):
        errors.append('Android host does not permit portrait and landscape orientations.')

if errors:
    print('PulseDeck verification FAILED:')
    for error in errors:
        print(' -', error)
    sys.exit(1)

print('PulseDeck static verification passed.')
print('Verified: four screens, both decks, Traktor-style faders, SAF whole-folder import with recursive scan and chunked reads, persistent folder permission, portrait/landscape host, EQ, sync, 138 BPM and Web Audio routing.')
