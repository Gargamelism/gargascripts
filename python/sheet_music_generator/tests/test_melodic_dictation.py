import pytest
from unittest.mock import patch, MagicMock
from music21 import stream, key, meter, note
from sheet_music_generator import helper
from sheet_music_generator.melodic_dictation.melodic_dictation import (
    generate_melodic_dictation_notes,
    generate_dictation_notes,
)


@patch("sheet_music_generator.melodic_dictation.melodic_dictation.RuleEngine")
def test_generate_melodic_dictation_notes(mock_rule_engine):
    mock_rule_engine.return_value.get_next_note.side_effect = lambda current_note, context: note.Note("D4")

    args = MagicMock()
    args.key = "C"
    args.time = "4/4"
    args.length = 8

    melody_stream = generate_melodic_dictation_notes(args)

    assert isinstance(melody_stream, stream.Stream), "Expected a music21 stream.Stream object"
    assert len(melody_stream.notes) == 12, f"Expected 12 notes (8 + 4 tonic notes), but got {len(melody_stream.notes)}"


@patch("sheet_music_generator.melodic_dictation.melodic_dictation.generate_melodic_dictation_notes")
def test_generate_dictation_notes(mock_generate_melodic_dictation_notes):
    mock_generate_melodic_dictation_notes.return_value = stream.Stream()

    args = ["--d-type", "melodic", "--scale-type", "major", "--time", "4/4", "--length", "8"]
    melody = generate_dictation_notes(args)

    assert melody.key in [
        "C",
        "G",
        "D",
        "A",
        "E",
        "B",
        "F#",
        "C#",
        "F",
        "Bb",
        "Eb",
        "Ab",
        "Db",
        "Gb",
        "Cb",
    ], f"Unexpected key: {melody.key}"
    assert melody.time_signature == "4/4", f"Expected time signature to be '4/4', but got {melody.time_signature}"
