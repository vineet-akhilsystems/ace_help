---
name: testing-voice-transcription
description: Use when testing or changing "Speak your day" / "Speak the tasks" voice input, the /transcribe endpoint, Sarvam speech-to-text, SARVAM_MODEL, audio formats, or when voice notes come back empty, garbled or as "No speech was detected".
---

# Testing voice transcription

## Overview

Browser mic → `useRecorder` (`frontend/src/recorder.js`) → `POST /transcribe` (`backend/main.py`) →
`providers.transcribe` → Sarvam `https://api.sarvam.ai/speech-to-text`. The transcript is appended to the notes
box; nothing else happens until the user drafts.

## Facts to test against

| Stage | Behaviour |
|---|---|
| Recorder | first supported of `audio/webm;codecs=opus`, `audio/ogg;codecs=opus`, `audio/mp4`; stops itself at **28 s**; posts FormData field `audio`, filename `recording` |
| `/transcribe` | accepts `audio/webm`, `audio/ogg`, `audio/wav`, `audio/mp4`, `audio/mpeg`; other types → **415**; empty or > 10 MB → **413** |
| Sarvam call | header `api-subscription-key: SARVAM_API_KEY`; form `model=SARVAM_MODEL` (default `saarika:v2.5`), `language_code=unknown` (auto-detect, so Hindi/English mix works) |
| Empty transcript | `ProviderError('No speech was detected…')` → HTTP 502 with that text. Silence is transcribed as `""` (Sarvam guessed `kn-IN` for silence) |
| Sarvam HTTP error | 502 "Sarvam returned HTTP N. Check configuration or quota." — provider bodies are never passed on |

## Test layers (cheapest first)

1. **No network:** `tests/test_api.py::test_audio_validation` (415). For new cases, monkeypatch
   `backend.main.transcribe` (an async function) and post with `TestClient` and header `X-ACE-Client: 1`.
2. **Recorder UI:** Playwright can't reach a real mic; stub `**/transcribe` with `page.route` and check the
   transcript lands in the notes textarea (see verifying-ace-app).
3. **Live Sarvam (costs credits — ask the user first):** make real speech instead of recording:

```powershell
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Zira Desktop')          # installed voices: Microsoft David Desktop, Microsoft Zira Desktop (en-US only)
$s.SetOutputToWaveFile("$scratch\day.wav"); $s.Speak('Today I fixed the vitals template for doctors.'); $s.Dispose()
ffmpeg -loglevel error -y -i "$scratch\day.wav" -c:a libopus "$scratch\day.webm"   # what Chrome actually sends
```

Then call `providers.transcribe(data, 'day.webm', 'audio/webm')` from the venv, or post the file to the running
backend's `/transcribe`. There is no Hindi TTS voice on this machine; use a real recorded clip for Hindi/Hinglish.
This recipe has not yet been run end to end against Sarvam.

## Common mistakes

- Sending WAV only: the browser sends webm/opus, so test that format too.
- Treating a 502 as a crash: it is the designed path for provider failures and empty speech.
- Printing `SARVAM_API_KEY` or Sarvam responses into logs or files.
