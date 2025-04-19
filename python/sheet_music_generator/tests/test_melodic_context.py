import pytest
from sheet_music_generator.melodic_dictation.melodic_context import MelodicContext
from music21 import key, meter, stream


def test_melodic_context():
    test_key = key.Key("C")
    test_time_signature = meter.TimeSignature("4/4")
    context = MelodicContext(
        key=test_key,
        time_signature=test_time_signature,
        steps=[],
        melody_stream=stream.Stream(),
    )
    assert context.key == test_key
    assert context.time_signature == test_time_signature


def test_melodic_context_defaults():
    test_key = key.Key("C")
    test_time_signature = meter.TimeSignature("4/4")
    context = MelodicContext(
        key=test_key,
        time_signature=test_time_signature,
        steps=[],
        melody_stream=stream.Stream(),
    )
    assert context.tempo == 60, f"Expected default tempo to be 60, but got {context.tempo}"
    assert context.only_diatonic is True, f"Expected default only_diatonic to be True, but got {context.only_diatonic}"


def test_melodic_context_custom_values():
    test_key = key.Key("G")
    test_time_signature = meter.TimeSignature("3/4")
    test_stream = stream.Stream()
    context = MelodicContext(
        key=test_key,
        time_signature=test_time_signature,
        steps=["step1", "step2"],
        melody_stream=test_stream,
        tempo=120,
        only_diatonic=False,
    )
    assert context.key == test_key, f"Expected key to be {test_key}, but got {context.key}"
    assert (
        context.time_signature == test_time_signature
    ), f"Expected time signature to be {test_time_signature}, but got {context.time_signature}"
    assert (
        context.melody_stream == test_stream
    ), f"Expected melody_stream to be {test_stream}, but got {context.melody_stream}"
    assert context.steps == ["step1", "step2"], f"Expected steps to be ['step1', 'step2'], but got {context.steps}"
    assert context.tempo == 120, f"Expected tempo to be 120, but got {context.tempo}"
    assert context.only_diatonic is False, f"Expected only_diatonic to be False, but got {context.only_diatonic}"
