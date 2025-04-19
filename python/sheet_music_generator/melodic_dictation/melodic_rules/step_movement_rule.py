import random
from melodic_dictation.melodic_rules.melodic_base_rule import MelodicBaseRule


class StepUpMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.3):
        super().__init__(name="step_up_movement", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([1]), context)


class StepDownMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.3):
        super().__init__(name="step_down_movement", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([-1]), context)
