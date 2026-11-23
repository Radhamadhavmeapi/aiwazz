import json
import subprocess

import numpy as np
import soundfile as sf

from tests.conftest import speechlike
from tts import audio
from tts.text import MAX_PIECE, split_text

SR = 24000


def test_split_sentences_and_paragraphs():
    text = "नमस्ते दोस्तों! आज हम बात करेंगे। ठीक है?\n\nSecond para. \"Quoted.\" End"
    assert split_text(text) == [
        ["नमस्ते दोस्तों!", "आज हम बात करेंगे।", "ठीक है?"],
        ["Second para.", "\"Quoted.\"", "End"],
    ]


def test_long_sentence_is_limited():
    text = ("word " * 200).strip()
    pieces = split_text(text)[0]
    assert len(pieces) > 1 and all(len(p) <= MAX_PIECE for p in pieces)


def test_trim_keeps_edge_silence():
    pad = np.zeros(SR, dtype=np.float32)               # 1 s silence each side
    a = np.concatenate([pad, speechlike(1.0), pad])
    out = audio.trim_silence(a, SR, -45, keep_ms=100)
    assert abs(out.size / SR - 1.2) < 0.03              # 1 s speech + 2 × 100 ms


def test_trim_all_silence_is_empty():
    assert audio.trim_silence(np.zeros(SR, dtype=np.float32), SR, -45, 100).size == 0


def test_pad_edges_silent_and_faded():
    a = np.ones(SR, dtype=np.float32)
    out = audio.pad_edges(a, SR, pad_ms=80, fade_ms=10)
    assert out.size == SR + 2 * SR * 80 // 1000
    assert not out[: SR * 80 // 1000].any() and not out[-SR * 80 // 1000:].any()
    first = out[SR * 80 // 1000]
    assert first < 0.01 and out[SR // 2] == 1.0        # fade starts at ~0, middle untouched


def test_join_pauses():
    clip = np.ones(SR, dtype=np.float32)
    out = audio.join_segments([[clip, clip], [clip]], SR, 250, 600)
    assert out.size == 3 * SR + SR * 250 // 1000 + SR * 600 // 1000


def _measure(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                          "loudnorm=print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    return float(m["input_i"]), float(m["input_tp"])


def test_export_loudnorm_48k(tmp_path):
    a = speechlike(8.0, amp=0.02)                       # quiet input (~ -35 LUFS)
    loud = audio.export(a, SR, tmp_path / "x", sample_rate=48000, mp3_bitrate="192k",
                        target_lufs=-14.0, true_peak=-1.0)
    wav, mp3 = tmp_path / "x.wav", tmp_path / "x.mp3"
    info = sf.info(str(wav))
    assert info.samplerate == 48000 and info.subtype == "PCM_16" and info.channels == 1
    i, tp = _measure(wav)
    assert abs(i - -14.0) < 1.0 and tp <= -0.5
    assert loud.mode.startswith("linear") and loud.input_lufs < -25
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,bit_rate",
                            "-of", "json", str(mp3)], capture_output=True, text=True).stdout
    st = json.loads(probe)["streams"][0]
    assert st["sample_rate"] == "48000" and int(st["bit_rate"]) == 192000


def test_export_custom_target_and_skip(tmp_path):
    a = speechlike(6.0, amp=0.1)
    audio.export(a, SR, tmp_path / "y", sample_rate=48000, mp3_bitrate="192k",
                 target_lufs=-18.0, true_peak=-1.0)
    assert abs(_measure(tmp_path / "y.wav")[0] - -18.0) < 1.0
    loud = audio.export(a, SR, tmp_path / "z", sample_rate=48000, mp3_bitrate="192k",
                        target_lufs=None, true_peak=-1.0)
    assert loud.mode == "skipped" and (tmp_path / "z.mp3").exists()


def test_peaky_input_is_limited_not_dynamic(tmp_path):
    """Sparse clicks on quiet speech: reaching -14 LUFS needs limiting; must still hit target."""
    a = speechlike(5.0, amp=0.02)
    a[::4800] = 0.9                                        # 5 clicks per second near full scale
    loud = audio.export(a, SR, tmp_path / "p", sample_rate=48000, mp3_bitrate="192k",
                        target_lufs=-14.0, true_peak=-1.0)
    i, tp = _measure(tmp_path / "p.wav")
    assert loud.mode == "linear+limiter"
    assert abs(i - -14.0) < 0.5 and tp <= -1.0


def test_short_clip_hits_target(tmp_path):
    loud = audio.export(speechlike(1.5, amp=0.05), SR, tmp_path / "s", sample_rate=48000,
                        mp3_bitrate="192k", target_lufs=-16.0, true_peak=-1.0)
    assert abs(loud.output_lufs - -16.0) < 0.5 and loud.output_true_peak <= -1.0
