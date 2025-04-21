import random
from melodic_dictation.melodic_rules.melodic_base_rule import MelodicBaseRule


class SmallLeapUpMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.15):
        super().__init__(name="leap_up_movement", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([2, 3]), context)


class SmallLeapDownMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.15):
        super().__init__(name="leap_down_movement", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([-3, -2]), context)
