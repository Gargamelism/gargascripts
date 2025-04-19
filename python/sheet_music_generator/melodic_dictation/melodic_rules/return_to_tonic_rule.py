import random
from music21 import note
from melodic_dictation.melodic_rules.melodic_base_rule import MelodicBaseRule


class ReturnToTonicRule(MelodicBaseRule):
    def __init__(self, probability=0.1):
        super().__init__(name="return_to_tonic", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        # Get the scale degree of the previous note
        prev_scale_degree = context.key.getScaleDegreeFromPitch(prev_note, comparisonAttribute="step")

        # Determine weights based on proximity to prev_scale_degree
        distance_to_bottom_tonic = abs(prev_scale_degree - 1)
        distance_to_top_tonic = abs(prev_scale_degree - 8)

        # Assign higher weight to the closer tonic
        weights = [1 / (distance_to_bottom_tonic + 1), 1 / (distance_to_top_tonic + 1)]

        # Make a weighted random choice
        top_or_bottom_tonic = random.choices([1, 8], weights=weights)[0]

        # Calculate the number of half steps to the target scale degree
        half_steps = context.key.intervalBetweenDegrees(prev_scale_degree, top_or_bottom_tonic).semitones

        # Transpose the note by the calculated half steps
        new_note = prev_note.transpose(half_steps)

        context.steps.append(
            {
                "rule_name": self._name,
                "prev_note": prev_note,
                "new_note": new_note,
                "half_steps": half_steps,
            }
        )
        return new_note
