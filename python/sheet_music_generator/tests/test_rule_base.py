import pytest
from sheet_music_generator.rule_engine.rule_base import RuleBase


class TestRuleBase:
    class MockRuleBase(RuleBase):
        def condition(self, prev_step, context):
            return True

        def action(self, prev_step, context):
            return prev_step

    @pytest.fixture
    def mock_rule(self):
        return self.MockRuleBase(name="mock_rule", probability=0.75)

    def test_rule_base_attributes(self, mock_rule):
        assert mock_rule.name == "mock_rule", f"Expected rule name to be 'mock_rule', but got {mock_rule.name}"
        assert mock_rule.probability == 0.75, f"Expected probability to be 0.75, but got {mock_rule.probability}"

    def test_rule_base_condition_not_implemented(self):
        rule = RuleBase(name="base_rule")
        with pytest.raises(NotImplementedError, match="Subclasses should implement this method"):
            rule.condition(None, None)

    def test_rule_base_action_not_implemented(self):
        rule = RuleBase(name="base_rule")
        with pytest.raises(NotImplementedError, match="Subclasses should implement this method"):
            rule.action(None, None)

    def test_rule_base_str_representation(self, mock_rule):
        assert (
            str(mock_rule) == "Rule: mock_rule, Probability: 0.75"
        ), f"Unexpected string representation: {str(mock_rule)}"
