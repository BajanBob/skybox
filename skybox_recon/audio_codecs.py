"""Broadcast audio codec catalogue and conservative MPEG-TS stream hints.

This module identifies codec candidates from standard MPEG-TS stream_type values
and descriptor tags. It does not decode audio and does not claim that the ALi
M3510/M3510A silicon can decode every listed format.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodecInfo:
    key: str
    name: str
    family: str
    transport: str
    notes: str = ""


# DVB TS 101 154 V2.10.1 (2026-05) audio families, plus common IP playback
# formats useful to the optional Wi-Fi streaming/transcoding subsystem.
CODECS: tuple[CodecInfo, ...] = (
    CodecInfo("mpeg1-layer1", "MPEG-1 Audio Layer I", "MPEG audio", "DVB/TS"),
    CodecInfo("mpeg1-layer2", "MPEG-1 Audio Layer II", "MPEG audio", "DVB/TS"),
    CodecInfo("mpeg2-layer2-bc", "MPEG-2 Audio Layer II backward-compatible", "MPEG audio", "DVB/TS"),
    CodecInfo("aac-lc", "MPEG-4 AAC-LC", "AAC", "DVB/TS, IP"),
    CodecInfo("he-aac", "MPEG-4 HE-AAC (SBR)", "AAC", "DVB/TS, IP"),
    CodecInfo("he-aac-v2", "MPEG-4 HE-AAC v2 (SBR + PS)", "AAC", "DVB/TS, IP"),
    CodecInfo("mpeg-surround", "MPEG Surround", "MPEG immersive/surround", "DVB/TS"),
    CodecInfo("ac3", "Dolby Digital (AC-3)", "Dolby", "DVB/TS, ATSC"),
    CodecInfo("eac3", "Dolby Digital Plus (E-AC-3)", "Dolby", "DVB/TS, ATSC, IP"),
    CodecInfo("ac4", "Dolby AC-4", "Dolby next-generation audio", "DVB/TS, IP"),
    CodecInfo("dts", "DTS Digital Surround", "DTS", "DVB/TS"),
    CodecInfo("dts-hd", "DTS-HD", "DTS", "DVB/TS, IP"),
    CodecInfo("dts-uhd", "DTS-UHD", "DTS", "DVB/TS"),
    CodecInfo("mpeg-h-lc", "MPEG-H Audio (LC profile)", "MPEG-H", "DVB/TS"),
    CodecInfo("avs3-audio", "AVS3 Part 3 Audio", "AVS", "DVB/TS"),
    CodecInfo("amr-dvb", "AMR DVB", "AMR", "DVB metadata ecosystem"),
    CodecInfo("opus", "Opus", "Open audio", "IP/container playback; not a DVB TS 101 154 broadcast claim"),
    CodecInfo("vorbis", "Vorbis", "Open audio", "IP/container playback"),
    CodecInfo("flac", "FLAC", "Lossless", "IP/container playback"),
    CodecInfo("pcm", "Linear PCM", "Uncompressed", "IP/container/playback"),
)

_BY_KEY = {item.key: item for item in CODECS}

# MPEG-2 Systems stream_type values. Values with private/ambiguous carriage
# are intentionally not guessed without their PMT descriptors.
_STREAM_TYPES = {
    0x03: "mpeg1-layer2",  # MPEG-1 audio
    0x04: "mpeg2-layer2-bc",  # MPEG-2 audio
    0x0F: "aac-lc",  # AAC with ADTS framing; profile may refine this
    0x11: "aac-lc",  # MPEG-4 AAC LATM/LOAS; profile may refine this
    0x81: "ac3",  # ATSC AC-3 convention
    0x87: "eac3",  # ATSC E-AC-3 convention
}

# DVB descriptor tags commonly used in PMTs for audio identification.
_DESCRIPTOR_TAGS = {
    0x6A: "ac3",
    0x7A: "eac3",
    0x7B: "dts",
    0x7C: "aac-lc",  # AAC descriptor; inspect profile/extension for HE-AAC
}


def get_codec(key: str) -> CodecInfo | None:
    """Return a catalogue entry by stable key."""
    return _BY_KEY.get(key)


def list_codecs(transport: str | None = None) -> tuple[CodecInfo, ...]:
    """Return all codecs, optionally filtered by a transport label substring."""
    if transport is None:
        return CODECS
    needle = transport.casefold()
    return tuple(c for c in CODECS if needle in c.transport.casefold())


def identify_audio_candidate(stream_type: int, descriptor_tags: tuple[int, ...] = ()) -> CodecInfo | None:
    """Return a conservative codec candidate from a PMT elementary-stream entry.

    Descriptor evidence takes precedence over a generic stream_type. The caller
    must retain raw descriptors and may need codec-specific parsing to refine
    AAC profiles, AC-4, DTS variants, MPEG-H, and private stream carriage.
    """
    for tag in descriptor_tags:
        key = _DESCRIPTOR_TAGS.get(tag)
        if key:
            return _BY_KEY[key]
    key = _STREAM_TYPES.get(stream_type)
    return _BY_KEY.get(key) if key else None


def audio_codec_support_matrix() -> dict[str, str]:
    """Return the implementation status intended for the Skybox UI."""
    return {
        c.key: (
            "catalogued; detection requires PMT/descriptor parser and playback requires a decoder"
            if c.transport.startswith("DVB") or "DVB" in c.transport
            else "optional IP/container playback target; not DVB demodulator capability"
        )
        for c in CODECS
    }
