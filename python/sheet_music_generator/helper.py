import os
import random
from music21 import key, stream
from pydantic import BaseModel, ConfigDict


class Melody(BaseModel):
    notes: str = ""
    notes_stream: stream.Stream = None
    key: str = "C"
    time_signature: str = "4/4"
    tempo: int = 120

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
    )


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


def get_sound_font_path(sound_font_folder_path: str):
    """
    Get the sound font path
    """
    # Check if the sound font folder path is valid
    if not os.path.exists(sound_font_folder_path):
        raise ValueError(f"Sound font folder path {sound_font_folder_path} does not exist")

    # Get the sound font file path
    # get all files in the sound font folder
    sound_font_files = [file for file in os.listdir(sound_font_folder_path) if file.endswith(".sf2")]
    if not sound_font_files:
        raise ValueError(f"No sound font files found in {sound_font_folder_path}")

    sound_font_file = random.choice(sound_font_files)
    sound_font_file = os.path.join(sound_font_folder_path, sound_font_file)

    return sound_font_file
