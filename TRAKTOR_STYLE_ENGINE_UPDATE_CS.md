# PulseDeck – Traktor-style audio engine update

This update is an original implementation inspired by documented DJ-workflow behavior. It does not contain Native Instruments proprietary code.

## Changes in this update
- Removed the per-deck AnalyserNode from the live audio route. It was only used for a tooltip meter and forced FFT reads during frequent UI painting.
- Corrected EQ gain staging: neutral EQ (0 dB on all bands) now remains unity instead of muting the deck. The EQ controls continue to apply their configured dB values.
- Simplified deck painting so it updates playhead/time only and does not perform FFT work.
- Increased waveform peak-generation chunks from 8 to 32 bins to reduce timer churn during track loading.
- Reworked automatic phase correction to use a bounded, gradual rate trim around the master tempo ratio, with a small deadband and bounded integral term. It avoids routine buffer jumps during normal phase correction.
- Changed playback-rate smoothing to a short 40 ms target ramp and added an explicit immediate scheduling option.

## Verification performed
- `python scripts/verify_pulsedeck.py` – passed.
- `node scripts/test_dsp.js` – passed; synthetic 138 BPM test measured 137.99 BPM and beat offset error was about 2.3 ms.
- Extracted inline JavaScript passed `node --check`.
- ZIP integrity checked after packaging.

## Not yet verified
- Android APK build and device playback were not run in this environment.
- Phase correction has not yet been validated with two real music files on the target phone. The synthetic DSP test validates BPM/offset analysis, not full audio sync quality.
- Full Traktor feature parity (multiple editable grid markers, tempo-map editing, quantize/cue behavior and full EQ model selection) is not claimed by this update.
