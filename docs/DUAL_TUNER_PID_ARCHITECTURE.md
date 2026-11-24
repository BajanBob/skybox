# Skybox Recon — Dual Independent Tuner and Video-PID Architecture

**Selected hardware target:** two independent satellite tuner/demodulator paths.
**VID meaning:** video PID plus service identification (not USB Vendor ID).

This is the selected target architecture. It is not a claim that the currently
supplied ALi M3510/M3510A board or source code already exposes two independent
RF paths. The exact board revision, tuner ICs, demodulators, RF inputs, LNB
switching/distribution and transport-stream routes must be verified first.

## 1. Two genuinely independent receiver paths

Instantiate `TunerBackend A` and `TunerBackend B`. Each owns its own RF tuner,
demodulator, tuning state, lock metrics, TS input, scan queue and capability
report. The UI exposes separate frequency, polarization, symbol rate, standard,
MODCOD, SNR, MER, BER, lock and task status.

Default task policy:
- A: primary live-view / recording service.
- B: background blind scan, transponder survey or second live service.
- Allow swapping roles without losing each backend's state.
- A tuner may not silently borrow or mutate the other tuner's LNB/DiSEqC state.

Two independent RF paths require compatible RF/LNB distribution. A single
coax/LNB feed may impose polarization and band-switching constraints; use a
suitable independent LNB output, multiswitch or validated distribution system.
The coordinator must refuse dual-independent mode if either backend reports
`independent_rf_path = false`.

## 2. Service and video PID discovery

Interpret the user's VID requirement as **video PID and service identification**.
For each tuner transport stream, implement a standards-aware MPEG-TS parser:

1. PAT (PID 0): discover program/service IDs and PMT PIDs.
2. PMT: discover PCR PID, elementary stream PIDs, stream types and descriptors.
3. SDT: discover service names, provider names and service type.
4. NIT: collect network and transport metadata where present.
5. Validate section lengths, continuity counters, CRCs and table versions.

For every service expose service_id, service name, transport_stream_id,
original_network_id, PMT PID, PCR PID, video PID(s), video codec candidate,
audio PID(s), audio codec candidate, language, subtitle/data PIDs and CA state.
Retain unknown descriptors and unknown stream types rather than dropping them.
Do not claim a codec is decodable merely because its PID or descriptor is found.

## 3. Satellite identification versus service identification

Satellite/orbital-slot identification is a separate inference stage. Correlate
frequency, polarization, symbol rate, MODCOD, network_id, original_network_id,
transport_stream_id and known transponder catalogues. Show candidate orbital
slots with confidence and evidence. Never identify a satellite from video PID,
service name, frequency or signal strength alone.

## 4. Scan scheduling and cognitive behaviour

The cognitive scheduler arbitrates A/B work: foreground viewing, recording,
blind scan, low-symbol-rate SDR acquisition and background service discovery.
Protect active recordings and user-selected services. Adapt dwell time and retry
backoff using measured lock probability and signal quality. All automated actions
must have a reason, confidence, timestamp and outcome in the event log.
Require confirmation for disruptive LNB/DiSEqC changes, firmware operations and
flash writes. Never change an active tuner configuration without user consent.

## 5. Blind scan and very low symbol rates

Report capabilities per tuner backend. Hardware blind scan is available only if
the actual demodulator/driver supports it. SDR-assisted search is a separate path
and must report measured sample-rate, frequency-stability, filtering and decoder
limits. Do not advertise a universal minimum symbol rate without hardware tests.

## 6. Wi-Fi 6 audio/video output

The streaming service may select a service discovered by either tuner, remux its
transport stream or transcode through an optional media backend. Publish on the
local LAN over Wi-Fi 6; Wi-Fi 6 is transport, not a codec. Provide per-client
bitrate, latency, packet-loss and session controls. Probe installed decoders and
encoders at runtime; distinguish parsed, supported, software-decoded and
hardware-decoded formats.

## 7. Faceplate requirements

- Two tuner tiles with independent lock and scan controls.
- Combined scan scheduler with A/B assignment and conflict warnings.
- Service/PID browser grouped by tuner and service.
- Video PID, codec candidate, audio tracks, language, PCR/PMT and CA indicators.
- Satellite candidate list with evidence and confidence (not unsupported certainty).
- Wi-Fi AV client list and stream-health metrics.
- Capability page showing verified hardware versus planned software functions.

## 8. Implementation status

The accompanying `tuner_topology.py` supplies testable data models and a guard
that refuses dual mode unless both backends assert independent RF paths. It does
not implement hardware drivers, TS section parsing, blind scan, demodulation,
video decoding or Wi-Fi streaming. Those remain separate implementation tasks.
