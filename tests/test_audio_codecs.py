from skybox_recon.audio_codecs import get_codec, identify_audio_candidate, list_codecs


def test_catalog_includes_2026_dvb_families():
    keys = {c.key for c in list_codecs()}
    assert {"ac3", "eac3", "ac4", "dts", "dts-hd", "dts-uhd", "mpeg-h-lc", "avs3-audio", "he-aac-v2"} <= keys


def test_mpeg_ts_audio_hints():
    assert identify_audio_candidate(0x03).key == "mpeg1-layer2"
    assert identify_audio_candidate(0x0F).key == "aac-lc"
    assert identify_audio_candidate(0x06, (0x7A,)).key == "eac3"
    assert identify_audio_candidate(0x06, (0x6A,)).key == "ac3"
    assert identify_audio_candidate(0x99) is None


def test_codec_lookup():
    assert get_codec("ac4").name == "Dolby AC-4"
    assert get_codec("not-a-codec") is None
