import pytest
from music21 import note, key, meter, stream
from sheet_music_generator.melodic_dictation.melodic_rules.small_leap_movement_rule import (
    SmallLeapUpMovementRule,
    SmallLeapDownMovementRule,
)
from sheet_music_generator.melodic_dictation.melodic_context import MelodicContext


@pytest.fixture
def melodic_context():
    return MelodicContext(
        key=key.Key("C", "major"),
        time_signature=meter.TimeSignature("4/4"),
        steps=[],
        melody_stream=stream.Stream(),
    )


@pytest.fixture
def small_leap_up_rule():
    return SmallLeapUpMovementRule(probability=1.0)  # Ensure rule always applies for testing


@pytest.fixture
def small_leap_down_rule():
    return SmallLeapDownMovementRule(probability=1.0)  # Ensure rule always applies for testing


def test_small_leap_up_action(small_leap_up_rule, melodic_context):
    prev_note = note.Note("C4")
    modified_note = small_leap_up_rule.action(prev_note, melodic_context)
    assert modified_note.name in [
        "E",
        "F",
    ], f"Expected note name to be in ['E', 'F'], but got {modified_note.name}"


def test_small_leap_down_action(small_leap_down_rule, melodic_context):
    prev_note = note.Note("C4")
    modified_note = small_leap_down_rule.action(prev_note, melodic_context)
    assert modified_note.name in [
        "A",
        "G",
    ], f"Expected note name to be in ['A', 'G'], but got {modified_note.name}"
