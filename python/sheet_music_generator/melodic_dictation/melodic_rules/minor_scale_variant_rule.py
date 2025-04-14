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
        return context.key.mode == "minor" and len(context.steps) > 0 and prev_note is not None

    def action(self, prev_note, context: MelodicContext):
        # Get the note that was just created by another rule
        current_note = context.melody_stream.pop()

        # Create a copy to modify
        new_note = note.Note(current_note.pitch)

        # Decide whether to use harmonic or melodic minor characteristic notes
        variant = random.choice(["harmonic", "melodic"])
        modified = False

        if variant == "harmonic":
            # Harmonic minor's characteristic note is the raised 7th degree
            # Check if the current note is the 7th scale degree
            if new_note.step == context.key.pitchFromDegree(7).step:
                # There's a chance we'll raise it
                if random.random() < 0.7:
                    # Raise the 7th by a semitone
                    new_note = self._transpose_half_tone_up(new_note)
                    modified = True

        elif variant == "melodic":
            # Melodic minor's characteristic notes are raised 6th and 7th degrees ascending

            # Determine if we're in an ascending or descending passage
            if len(context.melody_stream.notes) >= (2 + context.time_signature.numerator):
                last_interval = context.notes[-1].midi - context.notes[-2].midi
                is_ascending = last_interval > 0
            else:
                is_ascending = random.choice([True, False])

            # Check if current note is 6th or 7th degree
            note_step = new_note.step
            sixth_degree = context.key.pitchFromDegree(6).step
            seventh_degree = context.key.pitchFromDegree(7).step

            if is_ascending and (note_step == sixth_degree or note_step == seventh_degree):
                # In ascending melodic minor, both 6th and 7th are raised
                if random.random() < 0.7:
                    new_note = self._transpose_half_tone_up(new_note)
                    modified = True

        # If we modified the note, log it
        if modified:
            # Remove the previous log entry
            prev_log_entry = context.steps.pop()

            # Add our modified log entry
            context.steps.append(
                {
                    "rule_name": self._name,
                    "prev_note": prev_note,
                    "new_note": new_note,
                    "interval": f"modified_from_{prev_log_entry.get('rule_name')}",
                }
            )
            return new_note

        # If we didn't modify the note, return the original note from the previous rule
        return current_note

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
