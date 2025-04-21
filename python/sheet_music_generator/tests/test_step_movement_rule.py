import pytest
from music21 import note, key, meter, stream
from sheet_music_generator.melodic_dictation.melodic_rules.step_movement_rule import (
    StepUpMovementRule,
    StepDownMovementRule,
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
def step_up_movement_rule():
    return StepUpMovementRule(probability=1.0)  # Ensure rule always applies for testing


@pytest.fixture
def step_down_movement_rule():
    return StepDownMovementRule(probability=1.0)  # Ensure rule always applies for testing


def test_step_up_condition(step_up_movement_rule, melodic_context):
    prev_note = note.Note("C")
    melodic_context.melody_stream.append(prev_note)
    assert step_up_movement_rule.condition(
        prev_note, melodic_context
    ), f"Expected condition to be True, but got False for context: {melodic_context}"


def test_step_up_action(step_up_movement_rule, melodic_context):
    prev_note = note.Note("C4")
    modified_note = step_up_movement_rule.action(prev_note, melodic_context)
    assert modified_note.name == "D", f"Expected note name to be 'D', but got {modified_note.name}"


def test_step_down_condition(step_down_movement_rule, melodic_context):
    prev_note = note.Note("E")
    melodic_context.melody_stream.append(prev_note)
    assert step_down_movement_rule.condition(
        prev_note, melodic_context
    ), f"Expected condition to be True, but got False for context: {melodic_context}"


def test_step_down_action(step_down_movement_rule, melodic_context):
    prev_note = note.Note("C4")
    modified_note = step_down_movement_rule.action(prev_note, melodic_context)
    assert modified_note.name == "B", f"Expected note name to be 'B', but got {modified_note.name}"
