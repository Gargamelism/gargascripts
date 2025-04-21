import pytest
from music21 import note, key, meter, stream
from sheet_music_generator.melodic_dictation.melodic_rules.melodic_base_rule import MelodicBaseRule
from sheet_music_generator.melodic_dictation.melodic_context import MelodicContext


class TestMelodicBaseRule:
    class MockMelodicBaseRule(MelodicBaseRule):
        def condition(self, prev_note, context):
            return True

        def action(self, prev_note, context):
            return prev_note

    @pytest.fixture
    def melodic_context(self):
        return MelodicContext(
            key=key.Key("C", "major"),
            time_signature=meter.TimeSignature("4/4"),
            steps=[],
            melody_stream=stream.Stream(),
        )

    @pytest.fixture
    def mock_rule(self):
        return self.MockMelodicBaseRule(name="mock_rule", probability=1.0)

    def test_get_note_by_interval_positive(self, mock_rule, melodic_context):
        prev_note = note.Note("C4")
        new_note = mock_rule._get_note_by_interval(prev_note, 2, melodic_context)
        assert new_note.name == "E", f"Expected note name to be 'E', but got {new_note.name}"

    def test_get_note_by_interval_negative(self, mock_rule, melodic_context):
        prev_note = note.Note("C4")
        new_note = mock_rule._get_note_by_interval(prev_note, -2, melodic_context)
        assert new_note.name == "A", f"Expected note name to be 'A', but got {new_note.name}"

    def test_get_note_by_interval_edge_case(self, mock_rule, melodic_context):
        prev_note = note.Note("C4")
        new_note = mock_rule._get_note_by_interval(prev_note, 0, melodic_context)
        assert new_note.name == "C", f"Expected note name to be 'C', but got {new_note.name}"
