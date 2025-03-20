#!/usr/bin/env python3
import argparse
from music21 import stream, key, meter, note, layout, tempo
import random
import sys
from pprint import pprint
import numpy as np
from dataclasses import dataclass


@dataclass
class Melody:
    notes: str
    key: str = "C"
    time_signature: str = "4/4"
    tempo: int = 120


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


def generate_solfege_notes(args) -> Melody:
    if args is None:
        args = []

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Solfege parameters")

    # Define the key signature
    keys = ["C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"]
    default_key = random.choice(keys)
    parser.add_argument("--key", "-k", default=default_key, help='Key signature (e.g., "C", "G", "F#")')

    time_signatures = ["3/4", "4/4"]
    default_time = random.choice(time_signatures)
    parser.add_argument("--time", "-t", default=default_time, help='Time signature (e.g., "4/4", "3/4")')

    parser.add_argument("--only_diatonic", "-d", default=True, action="store_true", help="Use only diatonic notes")

    parser.add_argument("--length", "-l", default=32, type=int, help="Number of notes in the melody")

    parsed_args, unkown_args = parser.parse_known_args(args)

    # Define the notes, octaves, and accidentals
    key_signature = key.Key(parsed_args.key)
    notes = get_key_notes(key_signature)
    octaves = ["4", "5"]
    accidentals = [""]
    accidentals_weights = [1.0]
    if not parsed_args.only_diatonic:
        accidentals.extend(["#", "b"])
        accidentals_weights = [0.8, 0.1, 0.1]  # Lower weight for accidentals

    notes = " ".join(
        [
            f"{np.random.choice(notes)}{np.random.choice(accidentals, p=accidentals_weights)}{np.random.choice(octaves)}-1.0"
            for _ in range(parsed_args.length)
        ]
    )

    return Melody(notes=notes, key=parsed_args.key, time_signature=parsed_args.time, tempo=60)


def generate_dictation_notes(args) -> Melody:
    if args is None:
        args = []

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Solfege parameters")

    # Define the key signature
    keys = ["C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"]
    default_key = random.choice(keys)
    parser.add_argument("--key", "-k", default=default_key, help='Key signature (e.g., "C", "G", "F#")')

    time_signatures = ["3/4", "4/4"]
    default_time = random.choice(time_signatures)
    parser.add_argument("--time", "-t", default=default_time, help='Time signature (e.g., "4/4", "3/4")')

    parser.add_argument("--only_diatonic", "-d", default=True, action="store_true", help="Use only diatonic notes")

    parser.add_argument("--length", "-l", default=8, type=int, help="Number of notes in the melody")

    parsed_args, unkown_args = parser.parse_known_args(args)

    # Define the notes, octaves, and accidentals
    key_signature = key.Key(parsed_args.key)
    notes = get_key_notes(key_signature)
    octaves = ["4", "5"]
    accidentals = [""]
    accidentals_weights = [1.0]
    if not parsed_args.only_diatonic:
        accidentals.extend(["#", "b"])
        accidentals_weights = [0.8, 0.1, 0.1]  # Lower weight for accidentals

    notes = " ".join(
        [
            f"{np.random.choice(notes)}{np.random.choice(accidentals, p=accidentals_weights)}{np.random.choice(octaves)}-1.0"
            for _ in range(parsed_args.length)
        ]
    )

    return Melody(notes=notes, key=parsed_args.key, time_signature=parsed_args.time, tempo=60)


def generate_rhythm_notes(args):
    if args is None:
        args = []

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Rhythm parameters")

    # Define the time signature
    time_signatures = ["3/4", "4/4"]
    default_time = random.choice(time_signatures)
    parser.add_argument("--time", "-t", default=default_time, help='Time signature (e.g., "4/4", "3/4")')

    # Define minimum and maximum note lengths
    parser.add_argument(
        "--min_length",
        "-min",
        default=0.5,
        type=float,
        help="Minimum note length in quarter notes (e.g., 0.5 for eighth note)",
    )

    parser.add_argument(
        "--max_length", "-max", type=float, help="Maximum note length in quarter notes (e.g., 4.0 for whole note)"
    )

    parser.add_argument("--length", "-l", default=32, type=int, help="Number of notes in the melody")

    parsed_args, unknown_args = parser.parse_known_args(args)

    # Determine the maximum note length based on the time signature
    if parsed_args.max_length is None:
        if parsed_args.time == "3/4":
            parsed_args.max_length = 3.0
        elif parsed_args.time == "4/4":
            parsed_args.max_length = 4.0

    # Generate random note lengths within the specified range
    note_lengths = []
    current_note_length = parsed_args.min_length
    while current_note_length <= parsed_args.max_length:
        current_note_length_str = str(current_note_length)
        note_lengths.append(current_note_length_str)
        note_lengths.append(f"r-{current_note_length_str}")
        current_note_length += 2

    # Create a distribution where all odd cells are higher than even cells
    weights = np.zeros(len(note_lengths))
    weights[1::2] = 0.2  # Higher weight for odd cells (rest notes)
    weights[0::2] = 0.8  # Lower weight for even cells (non-rest notes)
    weights /= weights.sum()  # Normalize to sum to 1

    notes = [np.random.choice(note_lengths, p=weights) for _ in range(parsed_args.length)]
    # Add B4 to non-rest notes
    notes = [note if "r-" in note else f"B4-{note}" for note in notes]

    return Melody(notes=" ".join(notes), time_signature=parsed_args.time, tempo=90)


def create_melody(melody_obj: Melody) -> stream.Stream:
    """
    Create a melody from a string of space-separated notes with durations
    Example format: "C4-1.0 D4-0.5 E4-0.5 F4-1.0 G4-1.0 A4-0.5 B4-0.5 C5-1.0"
    """

    # Create a new stream
    melody_stream = stream.Stream()

    # Set key and time signature
    melody_stream.append(key.Key(melody_obj.key))
    melody_stream.append(meter.TimeSignature(melody_obj.time_signature))

    # Set tempo
    melody_stream.append(tempo.MetronomeMark(number=melody_obj.tempo))

    # Add notes to the stream
    try:
        for note_str in melody_obj.notes.split():
            note_name, duration = note_str.split("-")
            # Handle rests
            if note_name.lower() == "r":
                note_obj = note.Rest()
            else:
                # Split the note and duration (e.g., "C4-1.0")
                note_obj = note.Note(note_name)

            note_obj.quarterLength = float(duration)
            melody_stream.append(note_obj)
    except Exception as e:
        print(f"Error creating melody: {e}, {note_str}")

    return melody_stream


def save_score(melody, output_format="musicxml", filename="output"):
    """
    Save the score in the specified format
    Supported formats: musicxml, midi, pdf
    """
    if output_format == "musicxml":
        melody.write("musicxml", f"{filename}.xml")
    elif output_format == "midi":
        melody.write("midi", f"{filename}.mid")
    elif output_format == "pdf":
        melody.write("lily.pdf", f"{filename}.pdf")


def main(args):
    parser = argparse.ArgumentParser(description="Generate a music score from command line")
    parser.add_argument(
        "--random_type",
        "-r",
        choices=["solfege", "rhythm", "dictation"],
        default="solfege",
        help="Type of random notes to generate",
    )

    parser.add_argument("--format", "-f", choices=["musicxml", "midi", "pdf"], default="musicxml", help="Output format")
    parser.add_argument("--output", "-o", default="output", help="Output filename (without extension)")
    parser.add_argument("--tempo", "-p", default=120, type=int, help="Tempo in beats per minute")

    args, sub_args = parser.parse_known_args(args)

    melody_obj = {
        "solfege": generate_solfege_notes,
        "rhythm": generate_rhythm_notes,
        "dictation": generate_dictation_notes,
    }.get(args.random_type)(sub_args)

    # Create and save the score
    melody_stream = create_melody(melody_obj)
    save_score(melody_stream, args.format, args.output)

    print(f"Score saved as '{args.output}.{args.format}'")


if __name__ == "__main__":
    main(sys.argv)
