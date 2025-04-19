import pytest
from unittest.mock import MagicMock
from music21 import note
from sheet_music_generator.rule_engine.rule_engine import RuleEngine
from sheet_music_generator.rule_engine.rule_base import RuleBase


class MockRule(RuleBase):
    def condition(self, prev_step, context):
        return True

    def action(self, prev_step, context):
        return note.Note("C4")


class MockRuleAlwaysTrue(RuleBase):
    def condition(self, prev_step, context):
        return True

    def action(self, prev_step, context):
        return note.Note("C4")


class MockRuleAlwaysFalse(RuleBase):
    def condition(self, prev_step, context):
        return False

    def action(self, prev_step, context):
        return note.Note("D4")


@pytest.fixture
def mock_context():
    return MagicMock()


@pytest.fixture
def rule_engine(mock_context):
    rules = [MockRule(name="mock_rule", probability=1.0)]
    return RuleEngine(rules=rules, context=mock_context)


def test_rule_engine():
    rules = [MockRule("MockRule", probability=1.0)]
    context = {}
    engine = RuleEngine(rules, context)
    prev_note = note.Note("D4")
    next_note = engine.get_next_note(prev_note, context)
    assert next_note.name == "C", f"Expected note name to be 'C', but got {next_note.name}"


def test_rule_engine_with_no_rules():
    rules = []
    context = {}
    engine = RuleEngine(rules, context)
    prev_note = note.Note("D4")
    next_note = engine.get_next_note(prev_note, context)
    assert next_note.name == "D", f"Expected note name to be 'D', but got {next_note.name}"


def test_rule_engine_with_multiple_rules():
    rules = [
        MockRuleAlwaysFalse("MockRuleFalse", probability=1.0),
        MockRuleAlwaysTrue("MockRuleTrue", probability=1.0),
    ]
    context = {}
    engine = RuleEngine(rules, context)
    prev_note = note.Note("D4")
    next_note = engine.get_next_note(prev_note, context)
    assert next_note.name == "C", f"Expected note name to be 'C', but got {next_note.name}"


def test_rule_engine_with_probabilities():
    rules = [
        MockRuleAlwaysTrue("MockRuleTrue", probability=0.0),
        MockRuleAlwaysTrue("MockRuleTrue", probability=1.0),
    ]
    context = {}
    engine = RuleEngine(rules, context)
    prev_note = note.Note("D4")
    next_note = engine.get_next_note(prev_note, context)
    assert next_note.name == "C", f"Expected note name to be 'C', but got {next_note.name}"


def test_add_rule(rule_engine):
    new_rule = MockRule(name="new_rule", probability=0.5)
    rule_engine.add_rule(new_rule)
    assert len(rule_engine._rules) == 2, "Expected 2 rules after adding a new rule"


def test_remove_rule(rule_engine):
    rule_engine.remove_rule("mock_rule")
    assert len(rule_engine._rules) == 0, "Expected 0 rules after removing the rule"


def test_get_next_note_with_applicable_rule(rule_engine, mock_context):
    prev_note = note.Note("G4")
    next_note = rule_engine.get_next_note(prev_note, mock_context)
    assert next_note.name == "C", f"Expected next note to be 'C', but got {next_note.name}"


def test_get_next_note_without_applicable_rule(mock_context):
    rule_engine = RuleEngine(rules=[], context=mock_context)
    prev_note = note.Note("G4")
    next_note = rule_engine.get_next_note(prev_note, mock_context)
    assert next_note.name == "G", f"Expected next note to be 'G', but got {next_note.name}"


def test_apply_post_processing(rule_engine, mock_context):
    post_rule = MockRule(name="post_rule", probability=1.0)
    rule_engine._post_process_rules.append(post_rule)
    result_note = rule_engine.apply_post_processing(note.Note("D4"), mock_context)
    assert result_note.name == "C", f"Expected post-processed note to be 'C', but got {result_note.name}"
