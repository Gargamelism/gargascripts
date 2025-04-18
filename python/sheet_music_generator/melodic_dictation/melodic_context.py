from dataclasses import dataclass
from music21 import note, key, meter, stream
from typing import List, Any, Optional


@dataclass
class MelodicContext:
    """Context for the rule engine"""

    key: key.Key
    time_signature: meter.TimeSignature
    notes: List[note.Note]
    steps: List[Any]
    tempo: int = 60
    only_diatonic: bool = True
    melody_stream: Optional[stream.Stream] = None
