"""Unit tests for the soundscape selection and muxing guards in video_generator.py.

These cover the deterministic selection and best-effort degradation paths; they
do not shell out to ffmpeg (the guard paths return before any subprocess call).
"""

import config
import video_generator as vg


class TestPickSoundscape:
    def test_returns_only_audio_files(self, tmp_path, monkeypatch):
        (tmp_path / "one.mp3").write_bytes(b"a")
        (tmp_path / "two.wav").write_bytes(b"b")
        (tmp_path / "notes.txt").write_text("ignore me")
        monkeypatch.setattr(config, "AUDIO_DIR", tmp_path)
        picks = {vg._pick_soundscape().name for _ in range(30)}
        assert picks and picks <= {"one.mp3", "two.wav"}

    def test_none_when_dir_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "AUDIO_DIR", tmp_path)
        assert vg._pick_soundscape() is None

    def test_none_when_dir_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "nope")
        assert vg._pick_soundscape() is None


class TestAddSoundscapeGuards:
    def test_no_ffmpeg_returns_original_untouched(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vg, "_ensure_ffmpeg_on_path", lambda: None)
        monkeypatch.setattr(vg.shutil, "which", lambda name: None)
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"VIDEO")
        assert vg._add_soundscape(video) == video
        assert video.read_bytes() == b"VIDEO"  # left silent, untouched

    def test_no_audio_files_returns_original_untouched(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vg, "_ensure_ffmpeg_on_path", lambda: None)
        monkeypatch.setattr(vg.shutil, "which", lambda name: "/usr/bin/ffmpeg")
        empty = tmp_path / "audio"
        empty.mkdir()
        monkeypatch.setattr(config, "AUDIO_DIR", empty)
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"VIDEO")
        assert vg._add_soundscape(video) == video
        assert video.read_bytes() == b"VIDEO"
