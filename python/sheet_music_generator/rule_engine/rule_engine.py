import random
from typing import Any
from music21 import scale, note

from rule_engine.rule_base import RuleBase


class RuleEngine:
    """Rule engine for determining the next note based on previous notes"""

    def __init__(self, rules: list[RuleBase], context: Any, post_prosess_rules: list[RuleBase] = None):
        self._rules = rules
        self._context = context
        self._post_process_rules = post_prosess_rules or []

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

    def apply_post_processing(self, note_obj: note.Note, context=None):
        """Apply all enabled post-processing rules to the note"""
        result = note_obj
        for rule in self._post_process_rules:
            if rule.condition:
                result = rule.action(result, context)
        return result

    def get_next_note(self, prev_note, context=None):
        """
        Determine the next note based on the rules and previous note

        Args:
            prev_note: The previous note (music21 Note object or note string)
            context: Additional context (e.g., key, time signature)

        Returns:
            music21 Note object
        """

        # Convert string to Note object if needed
        if isinstance(prev_note, str):
            prev_note = note.Note(prev_note)

        # Check each rule in order
        applicable_rules: list[RuleBase] = []
        for rule in self._rules:
            if rule.condition(prev_note, context):
                # Only apply the rule based on its probability
                if random.random() <= rule.probability:
                    applicable_rules.append(rule)

        # If no rules apply, return the same note
        chosen_note = note.Note(prev_note.nameWithOctave, type=prev_note.duration.type)

        # If we have applicable rules, choose one (weighted by probability)
        if applicable_rules:
            total_probability = sum(rule.probability for rule in applicable_rules)
            if total_probability <= 0:
                total_probability = 1

            # Normalize probabilities
            normalized_probs = [rule.probability / total_probability for rule in applicable_rules]

            # Choose a rule based on probability
            chosen_rule = random.choices(applicable_rules, weights=normalized_probs, k=1)[0]
            chosen_note = chosen_rule.action(prev_note, context)

        chosen_note = self.apply_post_processing(chosen_note, context)
        chosen_note.volume.velocity = random.randint(90, 120)

        return chosen_note
