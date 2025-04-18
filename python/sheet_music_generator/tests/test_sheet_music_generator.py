import pytest
from sheet_music_generator.sheet_music_generator import generate_solfege_notes, generate_rhythm_notes


def test_generate_solfege_notes():
    args = ["--key", "C", "--time", "4/4", "--length", "8"]
    melody = generate_solfege_notes(args)
    assert melody.key == "C"
    assert melody.time_signature == "4/4"
    assert len(melody.notes.split()) == 8


def test_generate_rhythm_notes():
    args = ["--time", "3/4", "--length", "6"]
    melody = generate_rhythm_notes(args)
    assert melody.time_signature == "3/4"
    assert len(melody.notes.split()) == 6
