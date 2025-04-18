import pytest
from sheet_music_generator.helper import get_key_notes, get_sound_font_path
from music21 import key
import os


def test_get_key_notes():
    test_key = key.Key("C")
    notes = get_key_notes(test_key)
    assert notes == ["C", "D", "E", "F", "G", "A", "B", "C"]


def test_get_sound_font_path(tmp_path):
    sound_font_folder = tmp_path / "soundfonts"
    sound_font_folder.mkdir()
    sound_font_file = sound_font_folder / "test.sf2"
    sound_font_file.write_text("dummy content")

    result = get_sound_font_path(str(sound_font_folder))
    assert result == str(sound_font_file)

    with pytest.raises(ValueError, match="No sound font files found"):
        empty_folder = tmp_path / "empty_soundfonts"
        empty_folder.mkdir()
        get_sound_font_path(str(empty_folder))

    with pytest.raises(ValueError, match="Sound font folder path .* does not exist"):
        get_sound_font_path("non_existent_folder")
