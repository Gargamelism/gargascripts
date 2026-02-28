import random
from .melodic_base_rule import MelodicBaseRule


class LargeLeapUpMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.15):
        super().__init__(name="leap_up_movement", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([4, 5, 6]), context)

    def post_action_probability(self) -> float:
        """After a large leap up we want to make sure we don't have another large leap up"""
        self.probability *= 0.5
        return self.probability


class LargeLeapDownMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.15):
        super().__init__(name="leap_down_movement", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([-4, -5, -6]), context)

    def post_action_probability(self) -> float:
        """After a large leap down we want to make sure we don't have another large leap down"""
        self.probability *= 0.5
        return self.probability
