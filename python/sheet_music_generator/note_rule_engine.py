import random
from music21 import note, scale, pitch, key, meter
from dataclasses import dataclass
from typing import Callable


@dataclass
class Context:
    """Context for the rule engine"""

    key: key.Key
    time_signature: meter.TimeSignature
    notes: list[note.Note]
    rules: list[str]
    tempo: int = 60
    only_diatonic: bool = True


class RuleBase:
    """Base class for rules in the rule engine"""

    def __init__(
        self,
        probability: float = 1.0,
    ):

        self._probability = probability

    def __str__(self):
        return f"Rule: {self._name}, Probability: {self._probability}"

    @property
    def name(self) -> str:
        return self._name

    def condition(self, prev_note: note.Note, context: Context) -> bool:
        raise NotImplementedError("Subclasses must implement the 'condition' method.")

    def action(self, prev_note: note.Note, context: Context) -> note.Note:
        raise NotImplementedError("Subclasses must implement the 'action' method.")

    @property
    def probability(self) -> float:
        return self._probability

    def _get_note_by_interval(self, prev_note: note.Note, interval_steps, context: Context):
        """Get a note by stepping a certain number of scale steps from previous note"""
        current_key = context.key

        new_note = prev_note.transpose(interval_steps)
        new_note.pitch.accidental = current_key.accidentalByStep(new_note.step)

        return new_note


class NoteRuleEngine:
    """Rule engine for determining the next note based on previous notes"""

    def __init__(self, rules: list[RuleBase], context: Context):
        self._rules = rules
        self._context = context if context else Context()

    def add_rule(self, rule: RuleBase):
        """
        Add a rule to the engine

        Args:
            name (str): Name of the rule
            condition (callable): Function that takes prev_note and returns bool
            action (callable): Function that takes prev_note and returns a new note
            probability (float): Probability of applying this rule when condition is met
        """
        self._rules.append(rule)

    def remove_rule(self, name):
        """Remove a rule by name"""
        self._rules = [rule for rule in self._rules if rule["name"] != name]

    def set_key(self, key_name):
        """Set the current key for the rule engine"""
        self.current_key = key_name
        self.default_scale = scale.MajorScale(key_name)

    def reset_rules(self, rules: list[RuleBase]):
        """Clear all rules"""
        self._rules = rules

    def get_next_note(self, prev_note, context=None):
        """
        Determine the next note based on the rules and previous note

        Args:
            prev_note: The previous note (music21 Note object or note string)
            context: Additional context (e.g., key, time signature)

        Returns:
            music21 Note object
        """
        if context is None:
            context = Context()

        # Convert string to Note object if needed
        if isinstance(prev_note, str):
            prev_note = note.Note(prev_note)

        # Check each rule in order
        applicable_rules = []
        for rule in self._rules:
            if rule.condition(prev_note, context):
                # Only apply the rule based on its probability
                if random.random() <= rule.probability:
                    applicable_rules.append(rule)

        # If we have applicable rules, choose one (weighted by probability)
        if applicable_rules:
            total_probability = sum(rule.probability for rule in applicable_rules)
            if total_probability <= 0:
                total_probability = 1

            # Normalize probabilities
            normalized_probs = [rule.probability / total_probability for rule in applicable_rules]

            # Choose a rule based on probability
            chosen_rule = random.choices(applicable_rules, weights=normalized_probs, k=1)[0]
            context.rules.append(str(chosen_rule))
            return chosen_rule.action(prev_note, context)

        # Fallback: just return the same note
        return note.Note(prev_note.nameWithOctave, type=prev_note.duration.type)


class StepMovementRule(RuleBase):
    def __init__(self, probability=0.6):
        super().__init__(
            probability=probability,
        )

        self._name = ("step_movement",)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([-2, -1, 1, 2]), context)


class LeapMovementRule(RuleBase):
    def __init__(self, probability=0.3):
        super().__init__(probability=probability)

        self._name = ("leap_movement",)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return self._get_note_by_interval(prev_note, random.choice([-5, -4, 3, 4, 5]), context)


class ReturnToTonicRule(RuleBase):
    def __init__(self, probability=0.1):
        super().__init__(probability=probability)

        self._name = ("return_to_tonic",)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return note.Note(context.notes[0])
