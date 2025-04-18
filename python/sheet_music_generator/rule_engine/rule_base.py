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

    @property
    def name(self) -> str:
        """Name of the rule"""
        return self._name

    @property
    def probability(self) -> float:
        """Probability of the rule being applied"""
        return self._probability

    def __str__(self):
        return f"Rule: {self._name}, Probability: {self._probability}"
