import pytest
from music21 import note, key, meter, stream
from sheet_music_generator.melodic_dictation.melodic_rules.return_to_tonic_rule import ReturnToTonicRule
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
def return_to_tonic_rule():
    return ReturnToTonicRule(probability=1.0)  # Ensure rule always applies for testing


def test_condition_always_true(return_to_tonic_rule, melodic_context):
    prev_note = note.Note("G")
    assert return_to_tonic_rule.condition(prev_note, melodic_context), "Expected condition to always be True"


def test_action_returns_to_closest_tonic(return_to_tonic_rule, melodic_context):
    prev_note = note.Note("G")
    melodic_context.melody_stream.append(prev_note)
    modified_note = return_to_tonic_rule.action(prev_note, melodic_context)
    assert modified_note.nameWithOctave in [
        "C",
        "C5",
    ], f"Expected note name to be 'C' or 'C5', but got {modified_note.name}"


def test_action_logs_steps(return_to_tonic_rule, melodic_context):
    prev_note = note.Note("G")
    melodic_context.melody_stream.append(prev_note)
    modified_note = return_to_tonic_rule.action(prev_note, melodic_context)
    assert len(melodic_context.steps) > 0, "Expected steps to be logged in the context"
    assert melodic_context.steps[-1]["rule_name"] == "return_to_tonic", "Expected rule name to be 'return_to_tonic'"
