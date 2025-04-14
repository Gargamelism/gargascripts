from dataclasses import dataclass
from music21 import note, key, meter, stream
from typing import Any


@dataclass
class MelodicContext:
    """Context for the rule engine"""

    key: key.Key
    time_signature: meter.TimeSignature
    notes: list[note.Note]
    steps: list[Any]
    tempo: int = 60
    only_diatonic: bool = True
    melody_stream: stream.Stream = None
