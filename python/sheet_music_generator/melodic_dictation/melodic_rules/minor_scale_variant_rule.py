from music21 import note
import random

from melodic_dictation.melodic_rules.melodic_base_rule import MelodicBaseRule
from melodic_dictation.melodic_context import MelodicContext


class MinorScaleVariantRule(MelodicBaseRule):
    """Rule that occasionally introduces notes from harmonic or melodic minor scales"""

    def __init__(self, probability=0.15):
        super().__init__(name="minor_scale_variant", probability=probability)

    def condition(self, prev_note, context: MelodicContext):
        # Only apply this rule if we're in a minor key
        return context.key.mode == "minor" and len(context.melody_stream.notes) > 0 and prev_note is not None

    def action(self, current_note: note.Note, context: MelodicContext):
        # Create a copy to modify
        new_note = note.Note(current_note.pitch)

        # if previous note is 6th and it is raised, and the current note is 7th then we must raise it
        prev_note = context.melody_stream[-1]
        prev_scale_degree = context.key.getScaleDegreeFromPitch(prev_note, comparisonAttribute="step")
        current_note_degree = context.key.getScaleDegreeFromPitch(current_note.pitch)

        # Check if previous note was the 6th scale degree and was raised
        # getScaleDegreeAndAccidentalFromPitch returns a tuple (scale_degree, accidental which signifies if it is raised or not)
        prev_was_raised_sixth = prev_scale_degree == 6 and (
            context.key.getScaleDegreeAndAccidentalFromPitch(prev_note.pitch)[1] is not None
        )

        # If previous note was a raised 6th and current is 7th, always raise the 7th
        if prev_was_raised_sixth and current_note_degree == 7:
            return self._transpose_half_tone_up(current_note)

        # Decide whether to use harmonic or melodic minor characteristic notes
        variant = random.choice(["harmonic", "melodic"])

        if variant == "harmonic":
            new_note = self._apply_harmonic_minor_variant(new_note, context)

        elif variant == "melodic":
            new_note = self._apply_melodic_minor_variant(new_note, context)

        # If we modified the note, log it
        if current_note.name != new_note.name:
            # Add our modified log entry
            context.steps.append(
                {
                    "rule_name": self._name,
                    "prev_note": current_note,
                    "new_note": new_note,
                    "interval": "raised_6th_or_7th",
                }
            )
            return new_note

        # If we didn't modify the note, return the original note from the previous rule
        return current_note

    def post_action_probability(self) -> float:
        """minor scale probability doesn't need to be adjusted"""
        return self.probability

    def _transpose_half_tone_up(self, some_note: note.Note):
        """Transpose the note up by a half tone keeping scale correctness."""
        accidental_name = "natural"
        if some_note.pitch.accidental is not None:
            accidental_name = some_note.pitch.accidental.name

        accidental_map = {
            "natural": f"{some_note.step}#",
            "sharp": f"{some_note.step}##",
            "flat": f"{some_note.step}",
            "double-flat": f"{some_note.step}b",
        }

        new_pitch_name = accidental_map.get(accidental_name)
        some_note.pitch.name = new_pitch_name
        return some_note

    def _apply_harmonic_minor_variant(self, current_note: note.Note, context: MelodicContext) -> note.Note:
        # Harmonic minor's characteristic note is the raised 7th degree
        # Check if the current note is the 7th scale degree
        if current_note.step == context.key.pitchFromDegree(7).step:
            # There's a chance we'll raise it
            if random.random() < 0.7:
                # Raise the 7th by a semitone
                return self._transpose_half_tone_up(current_note)

        return current_note

    def _apply_melodic_minor_variant(self, current_note: note.Note, context: MelodicContext) -> note.Note:
        # Melodic minor's characteristic notes are raised 6th and 7th degrees ascending

        # Determine if we're in an ascending or descending passage
        if len(context.melody_stream.notes) >= (2 + context.time_signature.numerator):
            last_interval = context.melody_stream.notes[-1].pitch.midi - context.melody_stream.notes[-2].pitch.midi
            is_ascending = last_interval > 0
        else:
            is_ascending = random.choice([True, False])

        # Check if current note is 6th or 7th degree
        current_note_step = current_note.step
        sixth_degree = context.key.pitchFromDegree(6).step
        seventh_degree = context.key.pitchFromDegree(7).step

        if is_ascending and (current_note_step == sixth_degree or current_note_step == seventh_degree):
            # In ascending melodic minor, both 6th and 7th are raised
            if random.random() < 0.7:
                current_note = self._transpose_half_tone_up(current_note)

        return current_note
