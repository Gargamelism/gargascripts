class RuleBase:
    """Base class for all rules in the rule engine"""

    def __init__(self, name: str, probability=0.5):
        self._probability = probability
        self._name = name

    def condition(self, prev_step, context):
        """Condition to check if the rule should be applied"""
        raise NotImplementedError("Subclasses should implement this method")

    def action(self, prev_step, context):
        """Action to perform if the condition is met"""
        raise NotImplementedError("Subclasses should implement this method")

    @property
    def name(self):
        """Name of the rule"""
        return self._name

    @property
    def probability(self):
        """Probability of the rule being applied"""
        return self._probability

    def __str__(self):
        return f"Rule: {self._name}, Probability: {self._probability}"
