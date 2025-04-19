from dataclasses import dataclass
from music21 import note, key, meter, stream
from typing import List, Any, Optional


@dataclass
class MelodicContext:
    """Context for the rule engine"""

    key: key.Key
    time_signature: meter.TimeSignature
    melody_stream: Optional[stream.Stream]
    steps: List[Any]
    tempo: int = 60
    only_diatonic: bool = True
