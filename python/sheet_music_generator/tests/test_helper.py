import argparse
import pytest
from music21 import key, stream
from sheet_music_generator.helper import Melody, get_key_notes, get_sound_font_path, positive_num
import os


@pytest.fixture
def temp_sound_font_folder(tmp_path):
    folder = tmp_path / "sound_fonts"
    folder.mkdir()
    (folder / "test1.sf2").write_text("dummy content")
    (folder / "test2.sf2").write_text("dummy content")
    return folder


def test_melody_defaults():
    melody = Melody()
    assert melody.notes == "", f"Expected notes to be an empty string, but got {melody.notes}"
    assert melody.key == "C", f"Expected key to be 'C', but got {melody.key}"
    assert melody.time_signature == "4/4", f"Expected time signature to be '4/4', but got {melody.time_signature}"
    assert melody.tempo == 120, f"Expected tempo to be 120, but got {melody.tempo}"


def test_melody_custom_values():
    melody_stream = stream.Stream()
    melody = Melody(notes="C D E", notes_stream=melody_stream, key="G", time_signature="3/4", tempo=90)
    assert melody.notes == "C D E", f"Expected notes to be 'C D E', but got {melody.notes}"
    assert melody.notes_stream == melody_stream, f"Expected notes_stream to match, but got {melody.notes_stream}"
    assert melody.key == "G", f"Expected key to be 'G', but got {melody.key}"
    assert melody.time_signature == "3/4", f"Expected time signature to be '3/4', but got {melody.time_signature}"
    assert melody.tempo == 90, f"Expected tempo to be 90, but got {melody.tempo}"


def test_get_key_notes():
    test_key = key.Key("C")
    notes = get_key_notes(test_key)
    assert notes == [
        "C",
        "D",
        "E",
        "F",
        "G",
        "A",
        "B",
        "C",
    ], f"Expected notes to be ['C', 'D', 'E', 'F', 'G', 'A', 'B', 'C'], but got {notes}"


def test_get_sound_font_path(temp_sound_font_folder):
    sound_font_path = get_sound_font_path(str(temp_sound_font_folder))
    assert sound_font_path.endswith(".sf2"), f"Expected a .sf2 file, but got {sound_font_path}"


def test_get_sound_font_path_no_files(tmp_path):
    empty_folder = tmp_path / "empty_fonts"
    empty_folder.mkdir()
    with pytest.raises(ValueError, match="No sound font files found"):
        get_sound_font_path(str(empty_folder))


def test_positive_num():
    assert positive_num("5") == 5, "Expected positive_num to return 5 for input '5'"
    with pytest.raises(argparse.ArgumentTypeError, match="Must be a positive number"):
        positive_num("-1")
