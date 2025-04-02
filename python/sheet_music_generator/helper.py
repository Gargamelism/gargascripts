from music21 import key, stream
from pydantic import BaseModel


class Melody(BaseModel):
    notes: str = ""
    notes_stream: stream.Stream = None
    key: str = "C"
    time_signature: str = "4/4"
    tempo: int = 120

    class Config:
        arbitrary_types_allowed = True


def get_key_notes(key_signature: key.Key) -> list:
    """
    Get the notes in a key signature
    """
    # Get the notes in the key signature
    notes = key_signature.pitches
    notes = [str(note) for note in notes]

    # Turn the - to b for flat notes
    notes = [note.replace("-", "b") for note in notes]

    # Remove the octave number
    notes = [note[:-1] for note in notes]

    return notes
