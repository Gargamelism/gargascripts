import logging
import argparse
import random
import numpy as np
from helper import Melody, get_key_notes
from music21 import key, stream, meter, note, tempo
from note_rule_engine import NoteRuleEngine, Context, ReturnToTonicRule, LeapMovementRule, StepMovementRule
from pprint import pformat

TEMPO = 60


def generate_melodic_dictation_notes(args) -> str:
    """
    Generate a melody using the rule engine

    Args:
        rule_engine: NoteRuleEngine instance
        start_note: Starting note (string or Note object)
        num_notes: Number of notes to generate
        key_sig: Key signature
        time_sig: Time signature

    Returns:
        music21 Stream object
    """

    context_key = key.Key(args.key)
    context = Context(
        key=context_key, time_signature=meter.TimeSignature(args.time), notes=context_key.pitches, steps=[]
    )
    rule_engine = NoteRuleEngine(
        rules=[
            StepMovementRule(probability=0.6),
            LeapMovementRule(probability=0.3),
            ReturnToTonicRule(probability=0.1),
        ],
        context=context,
    )

    # Create a new stream
    melody = stream.Stream()

    # Set key and time signature
    melody.append(context.key)
    melody.append(context.time_signature)
    melody.append(tempo.MetronomeMark(number=TEMPO))

    # establish the tonic note
    tonic_note = note.Note(context.key.tonic, type="quarter")
    melody.append(tonic_note)
    tonic_note = note.Note(context.key.tonic, type="quarter")
    melody.append(tonic_note)
    tonic_note = note.Note(context.key.tonic, type="quarter")
    melody.append(tonic_note)
    tonic_note = note.Note(context.key.tonic, type="quarter")
    melody.append(tonic_note)

    # Add the start note
    current_note = note.Note(random.choice(context.notes), type="quarter")
    melody.append(current_note)

    # Generate the rest of the notes
    for _ in range(args.length - 1):
        # Get the next note
        current_note = rule_engine.get_next_note(current_note, context)
        current_note.quarterLength = 1.0  # Default to quarter notes
        melody.append(current_note)

    logging.debug(f"Rules ran: {pformat(rule_engine._context.steps)}")

    return melody


def generate_dictation_notes(args) -> Melody:
    if args is None:
        args = []

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Solfege parameters")

    parser.add_argument("--d-type", "-dt", choices=["melodic"], default="melodic", help="Type of dictation to generate")

    # Define the key signature
    keys = ["C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"]
    default_key = random.choice(keys)
    parser.add_argument("--key", "-k", default=default_key, help='Key signature (e.g., "C", "G", "F#")')

    time_signatures = ["4/4"]
    default_time = random.choice(time_signatures)
    parser.add_argument(
        "--time", "-t", default=default_time, choices=["3/4", "4/4"], help='Time signature (e.g., "4/4", "3/4")'
    )

    parser.add_argument("--only_diatonic", "-d", default=True, action="store_true", help="Use only diatonic notes")

    parser.add_argument("--length", "-l", default=8, type=int, help="Number of notes in the melody")

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

    notes = {
        "melodic": generate_melodic_dictation_notes,
    }.get(
        parsed_args.d_type
    )(parsed_args)

    return Melody(notes_stream=notes, key=parsed_args.key, time_signature=parsed_args.time, tempo=60)
