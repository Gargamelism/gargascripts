from pprint import pprint
import pytest
from music21 import note, key, meter, stream
from sheet_music_generator.melodic_dictation.melodic_rules.minor_scale_variant_rule import MinorScaleVariantRule
from sheet_music_generator.melodic_dictation.melodic_context import MelodicContext


@pytest.fixture
def melodic_context():
    return MelodicContext(
        key=key.Key("a", "minor"),
        time_signature=meter.TimeSignature("4/4"),
        steps=[],
        melody_stream=stream.Stream(),
    )


@pytest.fixture
def minor_scale_variant_rule():
    return MinorScaleVariantRule(probability=1.0)  # Ensure rule always applies for testing


def test_condition_in_minor_key(minor_scale_variant_rule, melodic_context):
    prev_note = note.Note("A")
    melodic_context.melody_stream.append(prev_note)
    assert minor_scale_variant_rule.condition(prev_note, melodic_context), "Expected condition to be True in minor key"


def test_condition_not_in_minor_key(minor_scale_variant_rule, melodic_context):
    melodic_context.key = key.Key("C", "major")
    prev_note = note.Note("A")
    melodic_context.melody_stream.append(prev_note)
    assert not minor_scale_variant_rule.condition(
        prev_note, melodic_context
    ), "Expected condition to be False in major key"


def test_action_raises_seventh_after_raised_sixth(minor_scale_variant_rule, melodic_context):
    melodic_context.melody_stream.append(note.Note("F#"))  # Raised 6th
    current_note = note.Note("G")  # 7th degree
    modified_note = minor_scale_variant_rule.action(current_note, melodic_context)
    assert modified_note.name == "G#", f"Expected note name to be 'G#', but got {modified_note.name}"


def test_action_harmonic_minor_variant(minor_scale_variant_rule, melodic_context):
    current_note = note.Note("G")  # 7th degree
    melodic_context.melody_stream.append(note.Note("F"))  # Previous note
    modified_note = minor_scale_variant_rule._apply_harmonic_minor_variant(current_note, melodic_context)
    assert modified_note.name in ["G", "G#"], f"Expected note name to be in ['G', 'G#'], but got {modified_note.name}"


def test_action_melodic_minor_variant(minor_scale_variant_rule, melodic_context):
    current_note = note.Note("F")  # 6th degree
    melodic_context.melody_stream.append(note.Note("E"))  # Previous note
    modified_note = minor_scale_variant_rule._apply_melodic_minor_variant(current_note, melodic_context)
    assert modified_note.name in ["F", "F#"], f"Expected note name to be in ['F', 'F#'], but got {modified_note.name}"
