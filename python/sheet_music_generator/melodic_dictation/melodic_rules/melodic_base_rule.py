from music21 import note, key

from rule_engine.rule_base import RuleBase
from melodic_dictation.melodic_context import MelodicContext


class MelodicBaseRule(RuleBase):
    """Base class for rules in the rule engine"""

    def __init__(
        self,
        name: str,
        probability: float = 1.0,
    ):

        super().__init__(name=name, probability=probability)

    def condition(self, prev_note: note.Note, context: MelodicContext) -> bool:
        raise NotImplementedError("Subclasses must implement the 'condition' method.")

    def action(self, prev_note: note.Note, context: MelodicContext) -> note.Note:
        raise NotImplementedError("Subclasses must implement the 'action' method.")

    @property
    def probability(self) -> float:
        return self._probability

    def _get_note_by_interval(self, prev_note: note.Note, interval_steps: int, context: MelodicContext) -> note.Note:
        """Get a note by stepping a certain number of scale steps from previous note"""

        # Get the scale degree of the previous note
        prev_scale_degree = context.key.getScaleDegreeFromPitch(prev_note, comparisonAttribute="step")

        # Calculate the number of half steps to the target scale degree
        half_steps = context.key.intervalBetweenDegrees(prev_scale_degree, interval_steps).semitones

        # Transpose the note by the calculated half steps
        new_note = prev_note.transpose(half_steps)

        context.steps.append(
            {
                "rule_name": self._name,
                "prev_note": prev_note,
                "new_note": new_note,
                "interval": interval_steps,
            }
        )

        return new_note
