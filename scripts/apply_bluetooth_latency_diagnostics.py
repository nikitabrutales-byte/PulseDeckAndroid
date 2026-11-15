#!/usr/bin/env python3
"""Guarded PulseDeck Bluetooth route diagnostics + WebAudio wake-up patch.
Run from the PulseDeckAndroid repository root:
    python scripts/apply_bluetooth_latency_diagnostics.py
Does not force Bluetooth SCO and does not change the UI.
"""
from pathlib import Path
import hashlib

EXPECTED_ACTIVITY = "fd0052678167b82d4e0b176914f7e37e135362ed"
TARGETS = ("app/src/main/assets/index.html", "app/src/main/java/com/pulsedeck/dj/MainActivity.kt")

def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def replace_once(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"STOP: {label}: expected one match, found {n}; no files changed.")
    return src.replace(old, new, 1)

def main():
    root = Path.cwd().resolve()
    files = {name: root / name for name in TARGETS}
    for name, path in files.items():
        if not path.is_file():
            raise SystemExit(f"STOP: missing {name}; run from repository root.")
    originals = {name: path.read_bytes() for name, path in files.items()}
    activity_path = "app/src/main/java/com/pulsedeck/dj/MainActivity.kt"
    actual = blob_sha(originals[activity_path])
    if actual != EXPECTED_ACTIVITY:
        raise SystemExit(f"STOP: {activity_path} revision mismatch; no files changed. Expected {EXPECTED_ACTIVITY}, found {actual}.")

    html = originals["app/src/main/assets/index.html"].decode("utf-8")
    kt = originals["app/src/main/java/com/pulsedeck/dj/MainActivity.kt"].decode("utf-8")

    kt = replace_once(kt, "import android.database.Cursor\n",
        "import android.database.Cursor\nimport android.media.AudioDeviceCallback\nimport android.media.AudioDeviceInfo\nimport android.media.AudioManager\nimport android.os.Handler\nimport android.os.Looper\n",
        "Android audio imports")
    kt = replace_once(kt, "    private var persistentLibraryTreeUri: Uri? = null\n",
        "    private var persistentLibraryTreeUri: Uri? = null\n    private var audioDeviceCallback: AudioDeviceCallback? = null\n    private var audioManager: AudioManager? = null\n",
        "audio callback fields")

    close = """        }
    }

    private fun findChildDocument"""
    inserted = """        }

        @JavascriptInterface
        fun getAudioRouteInfo(): String {
            return try {
                val manager = getSystemService(AUDIO_SERVICE) as AudioManager
                val outputs = manager.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
                val connected = JSONArray()
                outputs.forEach { device ->
                    connected.put(JSONObject().apply {
                        put("type", audioDeviceTypeName(device.type))
                        put("isSink", device.isSink)
                    })
                }
                val bluetoothTypes = setOf(AudioDeviceInfo.TYPE_BLUETOOTH_A2DP,
                    AudioDeviceInfo.TYPE_BLUETOOTH_SCO, AudioDeviceInfo.TYPE_BLE_HEADSET,
                    AudioDeviceInfo.TYPE_BLE_SPEAKER)
                JSONObject().apply {
                    put("connectedOutputs", connected)
                    put("bluetoothOutputConnected", outputs.any { it.type in bluetoothTypes })
                    put("outputSampleRateHz", manager.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE)?.toIntOrNull() ?: JSONObject.NULL)
                    put("outputFramesPerBuffer", manager.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER)?.toIntOrNull() ?: JSONObject.NULL)
                    put("audioMode", manager.mode)
                    put("lowLatencyFeature", packageManager.hasSystemFeature(android.content.pm.PackageManager.FEATURE_AUDIO_LOW_LATENCY))
                    put("proAudioFeature", packageManager.hasSystemFeature(android.content.pm.PackageManager.FEATURE_AUDIO_PRO))
                    put("routingNote", "Connected outputs are reported; Android selects the active media route.")
                }.toString()
            } catch (e: Exception) {
                android.util.Log.e("PulseDeck", "Audio route diagnostics failed", e)
                JSONObject().put("error", e.message ?: "unknown").toString()
            }
        }
    }

    private fun audioDeviceTypeName(type: Int): String = when (type) {
        AudioDeviceInfo.TYPE_BUILTIN_SPEAKER -> "BUILTIN_SPEAKER"
        AudioDeviceInfo.TYPE_BUILTIN_EARPIECE -> "BUILTIN_EARPIECE"
        AudioDeviceInfo.TYPE_WIRED_HEADPHONES -> "WIRED_HEADPHONES"
        AudioDeviceInfo.TYPE_WIRED_HEADSET -> "WIRED_HEADSET"
        AudioDeviceInfo.TYPE_USB_DEVICE -> "USB_DEVICE"
        AudioDeviceInfo.TYPE_USB_HEADSET -> "USB_HEADSET"
        AudioDeviceInfo.TYPE_HDMI -> "HDMI"
        AudioDeviceInfo.TYPE_BLUETOOTH_A2DP -> "BLUETOOTH_A2DP"
        AudioDeviceInfo.TYPE_BLUETOOTH_SCO -> "BLUETOOTH_SCO"
        AudioDeviceInfo.TYPE_BLE_HEADSET -> "BLE_HEADSET"
        AudioDeviceInfo.TYPE_BLE_SPEAKER -> "BLE_SPEAKER"
        else -> "OTHER_$type"
    }

    private fun registerAudioDeviceCallback() {
        if (audioDeviceCallback != null) return
        val manager = getSystemService(AUDIO_SERVICE) as AudioManager
        audioManager = manager
        val callback = object : AudioDeviceCallback() {
            override fun onAudioDevicesAdded(addedDevices: Array<out AudioDeviceInfo>?) { notifyAudioRouteChanged() }
            override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>?) { notifyAudioRouteChanged() }
        }
        audioDeviceCallback = callback
        manager.registerAudioDeviceCallback(callback, Handler(Looper.getMainLooper()))
        notifyAudioRouteChanged()
    }

    private fun unregisterAudioDeviceCallback() {
        val callback = audioDeviceCallback ?: return
        try { audioManager?.unregisterAudioDeviceCallback(callback) } catch (_: Exception) {}
        audioDeviceCallback = null
    }

    private fun notifyAudioRouteChanged() {
        if (!::webView.isInitialized) return
        webView.post {
            if (!::webView.isInitialized) return@post
            webView.evaluateJavascript("window.onPulseDeckAudioRouteChanged && window.onPulseDeckAudioRouteChanged()", null)
        }
    }

    private fun findChildDocument"""
    kt = replace_once(kt, close, inserted, "native route bridge")

    kt = replace_once(kt,
        "    override fun onResume() { super.onResume(); if (::webView.isInitialized) hideSystemBars() }\n",
        "    override fun onResume() { super.onResume(); if (::webView.isInitialized) hideSystemBars(); registerAudioDeviceCallback() }\n"
        "    override fun onPause() { unregisterAudioDeviceCallback(); super.onPause() }\n",
        "audio callback lifecycle")
    kt = replace_once(kt, "    override fun onDestroy() {\n",
        "    override fun onDestroy() {\n        unregisterAudioDeviceCallback()\n",
        "audio callback cleanup")

    html = replace_once(html,
        "ctx=new(window.AudioContext||window.webkitAudioContext)({latencyHint:'interactive'});",
        "ctx=new(window.AudioContext||window.webkitAudioContext)({latencyHint:'interactive'});ctx.onstatechange=()=>refreshPulseDeckAudioDiagnostics();",
        "AudioContext state hook")
    old_warm = """// Warm the audio engine on the user's first real interaction, before PLAY is pressed.
function warmAudioEngine(){try{ensureEngine().catch(()=>{});}catch(_){}}
document.addEventListener('pointerdown',warmAudioEngine,{once:true,passive:true});
document.addEventListener('touchstart',warmAudioEngine,{once:true,passive:true});
document.addEventListener('keydown',warmAudioEngine,{once:true});
"""
    new_warm = """// Keep the engine ready after gestures and when the app returns to foreground.
function warmAudioEngine(){
 try{const p=ensureEngine();if(p&&typeof p.catch==='function')p.catch(e=>console.warn('PulseDeck audio resume failed',e));}
 catch(e){console.warn('PulseDeck audio activation failed',e)}
}
function refreshPulseDeckAudioDiagnostics(){
 const nativeInfo={};
 try{if(window.PulseDeckAndroid&&typeof window.PulseDeckAndroid.getAudioRouteInfo==='function')
  Object.assign(nativeInfo,JSON.parse(window.PulseDeckAndroid.getAudioRouteInfo()||'{}'));}
 catch(e){nativeInfo.error=String(e)}
 const info={contextState:ctx?ctx.state:'not-created',sampleRateHz:ctx?ctx.sampleRate:null,
  baseLatencySeconds:ctx&&Number.isFinite(ctx.baseLatency)?ctx.baseLatency:null,
  outputLatencySeconds:ctx&&Number.isFinite(ctx.outputLatency)?ctx.outputLatency:null,
  latencyHint:'interactive-requested',native:nativeInfo,measuredAt:new Date().toISOString()};
 window.PulseDeckAudioDiagnostics=info;
 try{console.info('PulseDeck audio diagnostics',info)}catch(_){}
 return info;
}
window.onPulseDeckAudioRouteChanged=refreshPulseDeckAudioDiagnostics;
window.refreshPulseDeckAudioDiagnostics=refreshPulseDeckAudioDiagnostics;
document.addEventListener('pointerdown',warmAudioEngine,{capture:true,passive:true});
document.addEventListener('keydown',warmAudioEngine,{capture:true});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)warmAudioEngine();});
window.addEventListener('pageshow',warmAudioEngine);
window.addEventListener('focus',warmAudioEngine);
"""
    html = replace_once(html, old_warm, new_warm, "WebAudio wake-up and diagnostics")

    checks = [
        ("interactive mode", "latencyHint:'interactive'" in html),
        ("pointer capture", "pointerdown',warmAudioEngine,{capture:true" in html),
        ("visibility resume", "visibilitychange',()=>{if(!document.hidden)warmAudioEngine()" in html),
        ("base latency", "baseLatencySeconds" in html),
        ("output latency", "outputLatencySeconds" in html),
        ("native bridge", "fun getAudioRouteInfo(): String" in kt),
        ("A2DP reporting", "TYPE_BLUETOOTH_A2DP" in kt),
        ("BLE reporting", "TYPE_BLE_HEADSET" in kt and "TYPE_BLE_SPEAKER" in kt),
        ("device callback", "registerAudioDeviceCallback" in kt),
        ("no forced SCO", "startBluetoothSco" not in kt and "setCommunicationDevice" not in kt),
    ]
    failed = [name for name, ok in checks if not ok]
    if failed:
        raise SystemExit("STOP: validation failed: " + ", ".join(failed) + "; no files changed.")

    backups = {}
    for name, path in files.items():
        backup = path.with_name(path.name + ".before_bt_latency_diagnostics.bak")
        if backup.exists():
            raise SystemExit(f"STOP: backup already exists: {backup}; no files changed.")
        backups[name] = backup
    for name, data in originals.items():
        backups[name].write_bytes(data)
    files["app/src/main/assets/index.html"].write_text(html, encoding="utf-8")
    files["app/src/main/java/com/pulsedeck/dj/MainActivity.kt"].write_text(kt, encoding="utf-8")

    print("Applied Bluetooth/latency diagnostics patch.")
    print("Changed only index.html and MainActivity.kt; UI and audio graph are untouched.")
    print("Reports connected A2DP/SCO/BLE outputs, Android output sample-rate/buffer properties, WebAudio base/output latency.")
    print("Wakes/resumes WebAudio on touch, key, app foreground and focus return.")
    print("Does NOT force Bluetooth SCO or claim to remove Bluetooth codec latency.")
    print("Backups created beside both changed files.")
    print("Run scripts/verify_pulsedeck.py, node scripts/test_dsp.js, node scripts/test_browser.js, then assemble the APK.")

if __name__ == "__main__":
    main()
