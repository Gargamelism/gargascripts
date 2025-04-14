import random
from melodic_dictation.melodic_rules.melodic_base_rule import MelodicBaseRule


class StepMovementRule(MelodicBaseRule):
    def __init__(self, probability=0.6):
        super().__init__(
            name="step_movement",
            probability=probability,
        )

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        interval_steps = random.choice([-2, -1, 1, 2])
        return self._get_note_by_interval(prev_note, interval_steps, context)
