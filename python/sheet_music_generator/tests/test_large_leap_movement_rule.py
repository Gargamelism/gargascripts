import pytest
from music21 import note, key
from sheet_music_generator.melodic_dictation.melodic_rules.large_leap_movement_rule import (
    LargeLeapUpMovementRule,
    LargeLeapDownMovementRule,
)
from sheet_music_generator.melodic_dictation.melodic_context import MelodicContext


@pytest.fixture
def melodic_context():
    return MelodicContext(
        key=key.Key("C"),
        time_signature=None,
        steps=[],
        melody_stream=None,
    )


@pytest.fixture
def large_leap_up_rule():
    return LargeLeapUpMovementRule(probability=1.0)  # Ensure rule always applies for testing


@pytest.fixture
def large_leap_down_rule():
    return LargeLeapDownMovementRule(probability=1.0)  # Ensure rule always applies for testing


def test_large_leap_up_action(large_leap_up_rule, melodic_context):
    prev_note = note.Note("C4")
    modified_note = large_leap_up_rule.action(prev_note, melodic_context)
    assert modified_note.name in [
        "G",
        "A",
        "B",
    ], f"Expected note name to be in ['G', 'A', 'B'], but got {modified_note.name}"


def test_large_leap_down_action(large_leap_down_rule, melodic_context):
    prev_note = note.Note("C4")
    modified_note = large_leap_down_rule.action(prev_note, melodic_context)
    assert modified_note.name in [
        "F",
        "E",
        "D",
    ], f"Expected note name to be in ['F', 'E', 'D'], but got {modified_note.name}"
