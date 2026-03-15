"""
text_process: Extract text from documents, split into chunks, or get stats.

Usage:
    # Extract text from files
    python -m cc_layer.cli.text_process \
        --input-files resume.pdf cover_letter.txt \
        --mode extract \
        --output-file extracted.txt

    # Split text into chunks
    python -m cc_layer.cli.text_process \
        --input-text-file extracted.txt \
        --mode chunk \
        --chunk-size 2000 --overlap 200

    # Get text statistics
    python -m cc_layer.cli.text_process \
        --input-text-file extracted.txt \
        --mode stats

Output:
    extract: text to stdout or --output-file
    chunk: JSON array of chunks to stdout
    stats: JSON stats to stdout
"""
import argparse
import json
import sys

# Ensure backend is importable
import cc_layer.cli  # noqa: F401

from app.services.text_processor import TextProcessor


def main():
    parser = argparse.ArgumentParser(
        description="Text processing CLI (extract, chunk, stats)"
    )
    parser.add_argument(
        "--mode", choices=["extract", "chunk", "stats"],
        default="extract",
        help="Processing mode"
    )
    parser.add_argument(
        "--input-files", nargs="+",
        help="File paths to extract text from (mode=extract)"
    )
    parser.add_argument(
        "--input-text-file",
        help="Text file to process (mode=chunk/stats)"
    )
    parser.add_argument(
        "--input-text",
        help="Direct text input (mode=chunk/stats)"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=2000,
        help="Characters per chunk (mode=chunk)"
    )
    parser.add_argument(
        "--overlap", type=int, default=200,
        help="Overlap characters between chunks (mode=chunk)"
    )
    parser.add_argument(
        "--preprocess", action="store_true",
        help="Preprocess text (normalize whitespace/newlines)"
    )
    parser.add_argument(
        "--output-file",
        help="Write output to file instead of stdout"
    )

    args = parser.parse_args()

    try:
        if args.mode == "extract":
            if not args.input_files:
                parser.error("--input-files required for mode=extract")
            text = TextProcessor.extract_from_files(args.input_files)
            if args.preprocess:
                text = TextProcessor.preprocess_text(text)
            if args.output_file:
                with open(args.output_file, "w", encoding="utf-8") as f:
                    f.write(text)
                result = {
                    "status": "ok",
                    "output_file": args.output_file,
                    "chars": len(text),
                    "files_processed": len(args.input_files),
                }
                print(json.dumps(result, ensure_ascii=False))
            else:
                print(text)

        elif args.mode == "chunk":
            text = _read_input_text(args)
            if args.preprocess:
                text = TextProcessor.preprocess_text(text)
            chunks = TextProcessor.split_text(text, args.chunk_size, args.overlap)
            result = {
                "chunks": chunks,
                "count": len(chunks),
                "chunk_size": args.chunk_size,
                "overlap": args.overlap,
            }
            print(json.dumps(result, ensure_ascii=False))

        elif args.mode == "stats":
            text = _read_input_text(args)
            stats = TextProcessor.get_text_stats(text)
            print(json.dumps(stats, ensure_ascii=False))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _read_input_text(args) -> str:
    """Read text from --input-text-file or --input-text."""
    if args.input_text_file:
        with open(args.input_text_file, "r", encoding="utf-8") as f:
            return f.read()
    elif args.input_text:
        return args.input_text
    else:
        raise ValueError("--input-text-file or --input-text required for this mode")


if __name__ == "__main__":
    main()
