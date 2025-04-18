import pytest
from sheet_music_generator.rule_engine.rule_engine import RuleEngine
from sheet_music_generator.rule_engine.rule_base import RuleBase
from music21 import note


class MockRule(RuleBase):
    def condition(self, prev_step, context):
        return True

    def action(self, prev_step, context):
        return note.Note("C4")


def test_rule_engine():
    rules = [MockRule("MockRule", probability=1.0)]
    context = {}
    engine = RuleEngine(rules, context)
    prev_note = note.Note("D4")
    next_note = engine.get_next_note(prev_note, context)
    assert next_note.name == "C"
