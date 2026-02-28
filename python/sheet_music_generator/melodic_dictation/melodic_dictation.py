import logging
import argparse
import random
import numpy as np
from music21 import key, stream, meter, note, tempo
from pprint import pformat
from typing import List, Optional

from ..helper import Melody, positive_num
from ..rule_engine.rule_engine import RuleEngine
from .melodic_context import MelodicContext
from .melodic_rules.step_movement_rule import StepDownMovementRule, StepUpMovementRule
from .melodic_rules.small_leap_movement_rule import SmallLeapDownMovementRule, SmallLeapUpMovementRule
from .melodic_rules.medium_leap_movement_rule import (
    MediumLeapDownMovementRule,
    MediumLeapUpMovementRule,
)
from .melodic_rules.large_leap_movement_rule import (
    LargeLeapDownMovementRule,
    LargeLeapUpMovementRule,
)
from .melodic_rules.return_to_tonic_rule import ReturnToTonicRule
from .melodic_rules.minor_scale_variant_rule import MinorScaleVariantRule

TEMPO = 60


def generate_melodic_dictation_notes(args: argparse.Namespace) -> stream.Stream:
    """
    Generate a melody using the rule engine

    Args:
        args (argparse.Namespace): Parsed command-line arguments.

    Returns:
        stream.Stream: A music21 Stream object containing the generated melody.
    """

    context_key = key.Key(args.key)
    context = MelodicContext(
        key=context_key,
        time_signature=meter.TimeSignature(args.time),
        steps=[],
        melody_stream=stream.Stream(),
    )
    rule_engine = RuleEngine(
        rules=[
            StepDownMovementRule(probability=0.6),
            StepUpMovementRule(probability=0.6),
            SmallLeapDownMovementRule(probability=0.4),
            SmallLeapUpMovementRule(probability=0.4),
            MediumLeapDownMovementRule(probability=0.3),
            MediumLeapUpMovementRule(probability=0.3),
            LargeLeapDownMovementRule(probability=0.1),
            LargeLeapUpMovementRule(probability=0.1),
            ReturnToTonicRule(probability=0.1),
        ],
        context=context,
        post_prosess_rules=[MinorScaleVariantRule(probability=1)],
    )

    # Set key and time signature
    context.melody_stream.append(context.key)
    context.melody_stream.append(context.time_signature)
    context.melody_stream.append(tempo.MetronomeMark(number=TEMPO))

    # establish the tonic note
    tonic_note = note.Note(context.key.tonic, type="quarter")
    context.melody_stream.append(tonic_note)
    tonic_note = note.Note(context.key.tonic, type="quarter")
    context.melody_stream.append(tonic_note)
    tonic_note = note.Note(context.key.tonic, type="quarter")
    context.melody_stream.append(tonic_note)
    tonic_note = note.Note(context.key.tonic, type="quarter")
    context.melody_stream.append(tonic_note)

    # Add the start note
    current_note = note.Note(random.choice(context.key.pitches), type="quarter")
    context.melody_stream.append(current_note)

    # Generate the rest of the notes
    while len(context.melody_stream.notes) < (args.length + context.time_signature.numerator):
        # Get the next note
        current_note = rule_engine.get_next_note(current_note, context)
        current_note.quarterLength = 1.0  # Default to quarter notes
        context.melody_stream.append(current_note)

    logging.debug(f"Rules ran: {pformat(rule_engine._context.steps)}")

    return context.melody_stream


def generate_dictation_notes(args: Optional[List[str]]) -> Melody:
    """
    Generate dictation notes based on the provided arguments.

    Args:
        args (Optional[List[str]]): Command-line arguments for generating dictation notes.

    Returns:
        Melody: A Melody object containing the generated notes.
    """
    if args is None:
        args = []

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Solfege parameters")

    parser.add_argument("--key", "-k", default=None, type=str, help="Key signature (e.g., 'C', 'G#', 'db', etc.)")

    parser.add_argument("--d-type", "-dt", choices=["melodic"], default="melodic", help="Type of dictation to generate")

    parser.add_argument(
        "--scale-type",
        "-st",
        choices=["major", "minor", "both"],
        default="both",
        help="Scale type (e.g., 'major', 'minor', 'both')",
    )

    time_signatures = ["4/4"]
    default_time = random.choice(time_signatures)
    parser.add_argument(
        "--time", "-t", default=default_time, choices=["3/4", "4/4"], help='Time signature (e.g., "4/4", "3/4")'
    )

    parser.add_argument("--only_diatonic", "-d", default=True, action="store_true", help="Use only diatonic notes")

    parser.add_argument("--length", "-l", default=8, type=positive_num, help="Number of notes in the melody")

    default_octaves = ["4"]
    parser.add_argument(
        "--octaves",
        "-o",
        default=default_octaves,
        choices=["1", "2", "3", "4", "5", "6"],
        nargs="+",
        help="Octaves to use",
    )

    parsed_args, unkown_args = parser.parse_known_args(args)

    # Define the key signature
    major_keys = ["C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"]
    minor_keys = ["a", "e", "b", "f#", "c#", "g#", "d#", "db", "d", "g", "c", "f", "bb", "eb", "ab"]
    used_keys = (
        major_keys + minor_keys
        if parsed_args.scale_type == "both"
        else major_keys if parsed_args.scale_type == "major" else minor_keys
    )
    if parsed_args.key is None:
        parsed_args.key = random.choice(used_keys)
    if parsed_args.key not in used_keys:
        raise ValueError(f"Invalid key signature '{parsed_args.key}'. Must be one of {used_keys}.")

    notes = {
        "melodic": generate_melodic_dictation_notes,
    }.get(
        parsed_args.d_type
    )(parsed_args)

    return Melody(notes_stream=notes, key=parsed_args.key, time_signature=parsed_args.time, tempo=60)
