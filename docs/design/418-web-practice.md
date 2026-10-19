# 418 - Practice mode on the web

## Problem

The web opened the same practice screen as the phone, but the microphone was the
phone's own channel (`asr/shadowing_mic`, design/82) writing an M4A file into the
phone's temp folder. In a browser the channel does not exist and there is no temp
folder, so the speak phase failed on the first take. Replay read the same file.

## Shape

`services/shadow_mic.dart` is the one microphone the practice screen uses. A take
comes back as `MicTake` (bytes, content type, the phone's file path or none, and the
recorder's own length when it has one).

- Phone (`shadow_mic_io.dart`): the same channel calls as before. A prepared take
  (design/245) is used by the next speak start; the missed-word review starts its
  own take and leaves the prepared one alone, as before. The length is probed from
  the file, as before.
- Browser (`shadow_mic_web.dart`): `getUserMedia` plus `MediaRecorder`, WebM/Opus in
  Chrome and Edge, MP4 in Safari. The microphone stays open while the practice
  screen is open, so a take starts at once. Raw sound (no echo cancelling, noise
  suppression or gain control), like the phone's `MIC` source: the guide voice is
  silent while the user speaks (design/391), and processing would change what the
  model hears. The length is the recorder's own clock, because a browser WebM file
  carries no length to probe.

Replay plays the phone's file, or the browser's bytes with their content type. The
content type goes with the take to the local store, the voice blob, the take row and
the scoring upload.

The server decodes with ffmpeg either way; the temp file is named `.webm` when the
bytes start with the EBML header. `hear_mime_ok` counts WebM as expected.

A browser window goes inactive whenever another window takes focus, such as the
figure window on the second monitor (design/415). Practice on the web stops only
when the tab is hidden (`practicePausesOn`); the phone still stops on inactive.

## Not changed

The pass line is the account's own (design/375), shared by the phone and the web.
A PC microphone may sit at another level than the phone's; the line follows the
takes it sees, so it is not split by device.
