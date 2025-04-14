from music21 import note
from melodic_dictation.melodic_rules.melodic_base_rule import MelodicBaseRule


class ReturnToTonicRule(MelodicBaseRule):
    def __init__(self, probability=0.1):
        super().__init__(name="return_to_tonic", probability=probability)

    def condition(self, prev_note, context):
        return True

    def action(self, prev_note, context):
        return note.Note(context.notes[0])
