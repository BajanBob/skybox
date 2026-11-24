# Skybox Recon — Audio Codec Coverage (2026)

**Scope:** satellite broadcast audio carried in MPEG-2 Transport Streams, plus a separately labelled optional IP/container playback catalogue for the proposed Wi-Fi 6 streaming feature.

## DVB broadcast codec families to recognise

The current reference baseline is ETSI TS 101 154 V2.10.1 (May 2026). It identifies the following audio families for DVB broadcast/broadband receiver profiles:

- MPEG-1 Audio Layer I and Layer II
- MPEG-2 Layer II backward-compatible audio
- MPEG-4 AAC (including AAC-LC)
- MPEG-4 HE-AAC (SBR)
- MPEG-4 HE-AAC v2 (SBR + parametric stereo)
- MPEG Surround when carried with supported AAC/MPEG audio profiles
- Dolby AC-3 and Enhanced AC-3 (E-AC-3)
- Dolby AC-4, including channel-based and immersive/personalised service carriage
- DTS, DTS-HD and DTS-UHD
- MPEG-H Audio (LC profile)
- AVS3 Part 3 audio

DVB's metadata classification additionally lists AMR DVB. It should be recognised as a metadata/catalogue family where encountered, not presumed to be a common satellite television audio stream.

## Optional IP/container audio targets

For the planned Wi-Fi 6 receiver-to-device streaming path, the software playback/transcode layer may additionally support Opus, Vorbis, FLAC and Linear PCM. These are **not** to be presented as DVB TS 101 154 satellite broadcast codec support. Other formats can be added through a capability-probed decoder backend.

## Detection versus decoding

Skybox must keep these states separate in the UI and logs:

1. **Advertised/identified:** inferred from PMT stream_type and descriptors.
2. **Parsed:** codec-specific headers and profile information were successfully read.
3. **Decodable:** an installed, licensed and compatible decoder is available.
4. **Hardware-decoded:** the receiver chipset/firmware explicitly reports hardware decode support.
5. **Software-decoded:** a host-side decoder successfully decodes the selected stream.

A PID label or descriptor match is not proof of successful decoding. Preserve unknown private_stream_1 entries and raw descriptors rather than guessing a codec. AAC stream_type hints do not by themselves distinguish AAC-LC, HE-AAC and HE-AAC v2; profile refinement needs bitstream/configuration parsing.

## MPEG-TS metadata the service scanner should collect

For each program/service, retain PAT, PMT, SDT and NIT information where present; service_id, program_number, PMT PID, PCR PID, elementary PID, stream_type, descriptor bytes, ISO-639 language, component type, audio type, subtitle/teletext references, CA descriptors and scrambling state. For each audio PID, show language, codec candidate, profile/level when parsed, channel layout, sample rate and bitrate when available.

## Implementation status in this upload

`skybox_recon/audio_codecs.py` supplies a catalogue and conservative initial stream_type/descriptor hints. It is a foundation for the future full PMT parser and does **not** decode audio, parse every codec descriptor, or enable codecs in the ALi receiver. Unit tests cover the catalogue and conservative hints only.

## References

- ETSI TS 101 154 V2.10.1 (2026-05), *Specification for the use of Video and Audio Coding in Broadcast and Broadband Applications*: https://standards.iteh.ai/catalog/standards/etsi/73835ce1-9d91-4b02-b630-0c769bd03838/etsi-ts-101-154-v2-10-1-2026-05
- DVB, *Metadata — Audio codec classification scheme*: https://dvb.org/metadata/
- ETSI EN 300 468 V1.20.1 (2026-09), DVB Service Information, including AC-3/E-AC-3/AC-4, DTS/DTS-HD/DTS-UHD and AAC descriptors: https://www.iteh.eu/catalog/standards/etsi/2c47dd2a-2a6f-4175-b3cf-cb03ebc3a96c/etsi-en-300-468-v1-20-1-2026-09
- DASH-IF audio codec registrations for AAC, HE-AAC, HE-AAC v2, E-AC-3 and AC-4: https://dashif.org/codecs/audio/
