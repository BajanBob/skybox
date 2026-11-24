# Skybox Recon — Cognitive Receiver Architecture Addendum

This is a development specification, not a claim that the current ALi M3510/M3510A source implements these features.

## 1. Satellite/transponder discovery

Build a scan database of candidate orbital positions and transponders. Correlate measured IF/RF frequency, symbol rate, polarization, modulation, FEC, network_id, original_network_id, transport_stream_id and service information against a versioned satellite/transponder catalogue. Report a confidence score and evidence. Do not infer a satellite solely from frequency or signal strength; neighbouring orbital slots and reused frequencies make that unsafe.

## 2. Service and PID auto-discovery

Implement MPEG-TS section parsing with CRC validation and version tracking for PAT, PMT, SDT and NIT. Discover program/service IDs, PMT/PCR PIDs, video/audio/subtitle/data PIDs, language descriptors, component descriptors, CA descriptors and codec candidates. Preserve unknown descriptors for later analysis. Track PID changes and notify the user without interrupting a recording unless requested.

## 3. Agentic/cognitive control

Use a policy engine with observable evidence, confidence, bounded actions and a complete audit log. It may rank scan targets, adapt scan dwell time, propose symbol-rate/frequency corrections, detect lost lock, retry with bounded backoff, select a supported decoder and explain why. Require explicit confirmation for LNB voltage/tone, DiSEqC changes, firmware operations, flash writes and any operation that may disrupt an active service.

## 4. Dual-tuner abstraction

Define two independent `TunerBackend` instances, each with its own capabilities, RF path, LNB/DiSEqC topology, lock metrics, demodulator and TS output. Support independent scan/view assignments and resource arbitration. A second software object does not create a second physical tuner: simultaneous independent reception requires two genuine tuner/demodulator paths and compatible RF/LNB distribution. First verify the exact ALi board and silicon design; do not assume M3510/M3510A provides dual independent tuners.

## 5. Blind scan and extreme low symbol rates

Separate hardware blind-scan capability from SDR-assisted search. The receiver's demodulator limits determine the former. The SDR path may explore lower symbol rates only within the SDR's sample rate, filtering, oscillator stability, signal-to-noise ratio and decoder capabilities. Record actual tested minimum/maximum symbol rates per backend; never advertise a universal 100 sym/s floor without measurements.

## 6. Wi-Fi 6 software AV transmitter

Create a LAN-only streaming service fed from a decoded or remuxed transport stream. Include selectable services/PIDs, audio track selection, optional transcode, bitrate/resolution adaptation, client authentication, session limits, multicast/unicast choice and local discovery. Wi-Fi 6 is the network transport, not a codec or satellite demodulator. Use a pluggable media pipeline (for example FFmpeg/GStreamer when installed) and probe codecs at runtime. Do not assume hardware video/audio decode or encode is available.

## 7. UI panels

- Tuner A / Tuner B: frequency, polarization, SR, standard, MODCOD, lock, SNR/MER/BER and backend capability.
- Satellite discovery: candidate orbital slot, evidence, confidence, scan history.
- Service browser: service name/type, service_id, transport_stream_id, video PID/codec, audio PID/codec/language, PCR/PMT PID and CA state.
- Audio compatibility: identified / parsed / decodable / hardware-decoded / software-decoded status.
- Wi-Fi AV: local endpoint, clients, selected service/audio track, bitrate, dropped packets and latency.
- Cognitive event log: every recommendation/action, evidence, confidence, result and rollback state.

## 8. Hardware gate before claiming features

Obtain board revision, tuner count, demodulator count, demodulator datasheet, firmware interfaces, TS output route, USB bridge IDs and LNB/DiSEqC topology. Verify each feature on hardware. Current source remains a CLI toolkit with tuning/SDR/remux workflows; this addendum and the codec catalogue are not an implemented GUI, blind-scan engine, dual tuner, or Wi-Fi transmitter.
