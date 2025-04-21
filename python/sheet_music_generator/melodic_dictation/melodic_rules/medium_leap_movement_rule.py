import random
from melodic_dictation.melodic_rules.melodic_base_rule import MelodicBaseRule


class MediumLeapUpMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.15):
        super().__init__(name="leap_up_movement", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([3, 4]), context)


class MediumLeapDownMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.15):
        super().__init__(name="leap_down_movement", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([-4, -3]), context)
