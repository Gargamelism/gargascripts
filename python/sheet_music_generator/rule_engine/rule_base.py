from typing import Any
from music21 import note


class RuleBase:
    """Base class for all rules in the rule engine"""

    def __init__(self, name: str, probability: float = 0.5):
        self._probability: float = probability
        self._name: str = name

    def condition(self, prev_step: Any, context: Any) -> bool:
        """Condition to check if the rule should be applied"""
        raise NotImplementedError("Subclasses should implement this method")

    def action(self, prev_step: Any, context: Any) -> note.Note:
        """Action to perform if the condition is met"""
        raise NotImplementedError("Subclasses should implement this method")

    def post_action_probability(self) -> float:
        """Post action probability for the rule, should set self._probability and return it (for reference)"""
        # This method is a placeholder and should be implemented in subclasses
        raise NotImplementedError("Subclasses must implement the 'post_action_probability' method.")

    @property
    def name(self) -> str:
        """Name of the rule"""
        return self._name

    @property
    def probability(self) -> float:
        """Probability of the rule being applied"""
        return self._probability

    @probability.setter
    def probability(self, value: float) -> None:
        """Set the probability of the rule being applied"""
        if not (0 <= value <= 1):
            raise ValueError("Probability must be between 0 and 1")
        self._probability = value

    def __str__(self):
        return f"Rule: {self._name}, Probability: {self._probability}"
