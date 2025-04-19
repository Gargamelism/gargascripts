from unittest.mock import patch, MagicMock
import pytest
from music21 import stream, key, meter, note
from sheet_music_generator.sheet_music_generator import (
    generate_solfege_notes,
    generate_rhythm_notes,
    create_melody,
    midi_to_wav,
    wav_to_mp3,
    save_score,
)
from sheet_music_generator.helper import Melody


@patch("sheet_music_generator.sheet_music_generator.get_key_notes")
def test_generate_solfege_notes(mock_get_key_notes):
    mock_get_key_notes.return_value = ["C", "D", "E", "F", "G", "A", "B"]
    args = ["--key", "C", "--time", "4/4", "--length", "8"]
    melody = generate_solfege_notes(args)
    assert melody.key == "C", f"Expected key to be 'C', but got {melody.key}"
    assert melody.time_signature == "4/4", f"Expected time signature to be '4/4', but got {melody.time_signature}"
    assert len(melody.notes.split()) == 8, f"Expected 8 notes, but got {len(melody.notes.split())}"


@patch("sheet_music_generator.sheet_music_generator.get_key_notes")
def test_generate_rhythm_notes(mock_get_key_notes):
    args = ["--time", "3/4", "--length", "6"]
    melody = generate_rhythm_notes(args)
    assert melody.time_signature == "3/4", f"Expected time signature to be '3/4', but got {melody.time_signature}"
    assert len(melody.notes.split()) == 6, f"Expected 6 notes, but got {len(melody.notes.split())}"


@patch("sheet_music_generator.sheet_music_generator.logging")
def test_create_melody(mock_logging):
    melody_obj = Melody(notes="C4-1.0 D4-0.5", key="C", time_signature="4/4", tempo=120)
    melody_stream = create_melody(melody_obj)
    assert isinstance(melody_stream, stream.Stream), "Expected a music21 stream.Stream object"
    assert len(melody_stream.notes) == 2, f"Expected 2 notes, but got {len(melody_stream.notes)}"


@patch("sheet_music_generator.sheet_music_generator.subprocess.run")
def test_midi_to_wav(mock_subprocess_run):
    mock_subprocess_run.return_value = MagicMock()
    result = midi_to_wav("test.mid", "test.wav", "test.sf2")
    assert result is True, "Expected midi_to_wav to return True"


@patch("sheet_music_generator.sheet_music_generator.get_sound_font_path")
@patch("sheet_music_generator.sheet_music_generator.datetime")
def test_save_score(mock_datetime, mock_get_sound_font_path):
    mock_datetime.now.return_value.strftime.return_value = "2025-04-19_12-00"
    mock_get_sound_font_path.return_value = "test.sf2"
    melody = stream.Stream()
    melody.append(key.Key("C"))
    melody.append(meter.TimeSignature("4/4"))
    melody.append(note.Note("C4", quarterLength=1.0))
    result_path = save_score(melody, output_format="musicxml", filename="test_output", key="C")
    assert result_path.suffix == ".xml", f"Expected file extension to be '.xml', but got {result_path.suffix}"
