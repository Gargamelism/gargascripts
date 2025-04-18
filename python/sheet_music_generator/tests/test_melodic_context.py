import pytest
from sheet_music_generator.melodic_dictation.melodic_context import MelodicContext
from music21 import key, meter, note, stream


def test_melodic_context():
    test_key = key.Key("C")
    test_time_signature = meter.TimeSignature("4/4")
    test_notes = [note.Note("C4"), note.Note("D4")]
    context = MelodicContext(
        key=test_key,
        time_signature=test_time_signature,
        notes=test_notes,
        steps=[],
        melody_stream=stream.Stream(),
    )
    assert context.key == test_key
    assert context.time_signature == test_time_signature
    assert len(context.notes) == 2
