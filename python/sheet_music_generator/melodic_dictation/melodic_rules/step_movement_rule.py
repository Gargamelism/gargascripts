import random
from .melodic_base_rule import MelodicBaseRule


class StepUpMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.3):
        super().__init__(name="step_up_movement", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([1]), context)

    def post_action_probability(self) -> float:
        """Step up should decrease the probability of another step up a little bit"""
        self.probability *= 0.95
        return self.probability


class StepDownMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.3):
        super().__init__(name="step_down_movement", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([-1]), context)

    def post_action_probability(self) -> float:
        """Step down should decrease the probability of another step down a little bit"""
        self.probability *= 0.95
        return self.probability
