"""
graph_build: Build Zep knowledge graph from text + ontology.

Usage:
    # Build graph from text + ontology
    python -m cc_layer.cli.graph_build \
        --text-file extracted.txt \
        --ontology-file ontology.json \
        --graph-name "session_xxx" \
        --chunk-size 2000 --batch-size 5 \
        --output-file graph_info.json

    # Get existing graph info
    python -m cc_layer.cli.graph_build \
        --graph-id mirofish_abc123 --mode info

    # Get full graph data (nodes + edges)
    python -m cc_layer.cli.graph_build \
        --graph-id mirofish_abc123 --mode data

    # Delete graph
    python -m cc_layer.cli.graph_build \
        --graph-id mirofish_abc123 --mode delete

Output:
    JSON with graph_id, node_count, edge_count, entity_types
"""
import argparse
import json
import sys
import time

# Ensure backend is importable
import cc_layer.cli  # noqa: F401


def _build_graph(args):
    """Build a new graph (synchronous wrapper around async builder)."""
    from app.services.graph_builder import GraphBuilderService

    # Read inputs
    with open(args.text_file, "r", encoding="utf-8") as f:
        text = f.read()

    with open(args.ontology_file, "r", encoding="utf-8") as f:
        ontology = json.load(f)

    builder = GraphBuilderService()

    # Step 1: Create graph
    graph_id = builder.create_graph(args.graph_name or "MiroFish Graph")
    print(f"Graph created: {graph_id}", file=sys.stderr)

    # Step 2: Set ontology
    builder.set_ontology(graph_id, ontology)
    print("Ontology set", file=sys.stderr)

    # Step 3: Split text into chunks
    from app.services.text_processor import TextProcessor
    chunks = TextProcessor.split_text(text, args.chunk_size, args.overlap)
    print(f"Text split into {len(chunks)} chunks", file=sys.stderr)

    # Step 4: Add text batches
    def progress_cb(msg, prog):
        print(f"  {msg}", file=sys.stderr)

    episode_uuids = builder.add_text_batches(
        graph_id, chunks, args.batch_size, progress_cb
    )
    print(f"Sent {len(episode_uuids)} episodes", file=sys.stderr)

    # Step 5: Wait for processing
    print("Waiting for Zep to process...", file=sys.stderr)
    builder._wait_for_episodes(episode_uuids, progress_cb, timeout=args.timeout)

    # Step 6: Get graph info
    graph_info = builder._get_graph_info(graph_id)
    result = {
        "status": "ok",
        "graph_id": graph_id,
        "graph_info": graph_info.to_dict(),
        "chunks_processed": len(chunks),
    }

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(json.dumps({"status": "ok", "output_file": args.output_file, **graph_info.to_dict()}, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def _get_info(args):
    """Get graph info."""
    from app.services.graph_builder import GraphBuilderService
    builder = GraphBuilderService()
    info = builder._get_graph_info(args.graph_id)
    print(json.dumps(info.to_dict(), ensure_ascii=False, indent=2))


def _get_data(args):
    """Get full graph data."""
    from app.services.graph_builder import GraphBuilderService
    builder = GraphBuilderService()
    data = builder.get_graph_data(args.graph_id)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _delete_graph(args):
    """Delete a graph."""
    from app.services.graph_builder import GraphBuilderService
    builder = GraphBuilderService()
    builder.delete_graph(args.graph_id)
    print(json.dumps({"status": "ok", "deleted": args.graph_id}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="Build/manage Zep knowledge graphs"
    )
    parser.add_argument(
        "--mode", choices=["build", "info", "data", "delete"],
        default="build",
        help="Operation mode"
    )
    # Build mode args
    parser.add_argument("--text-file", help="Input text file (mode=build)")
    parser.add_argument("--ontology-file", help="Ontology JSON file (mode=build)")
    parser.add_argument("--graph-name", help="Graph name (mode=build)")
    parser.add_argument("--chunk-size", type=int, default=2000, help="Chunk size")
    parser.add_argument("--overlap", type=int, default=200, help="Chunk overlap")
    parser.add_argument("--batch-size", type=int, default=5, help="Batch size")
    parser.add_argument("--timeout", type=int, default=600, help="Processing timeout (sec)")
    parser.add_argument("--output-file", help="Write output to file")
    # Info/data/delete mode args
    parser.add_argument("--graph-id", help="Graph ID (mode=info/data/delete)")

    args = parser.parse_args()

    try:
        if args.mode == "build":
            if not args.text_file or not args.ontology_file:
                parser.error("--text-file and --ontology-file required for mode=build")
            _build_graph(args)

        elif args.mode == "info":
            if not args.graph_id:
                parser.error("--graph-id required for mode=info")
            _get_info(args)

        elif args.mode == "data":
            if not args.graph_id:
                parser.error("--graph-id required for mode=data")
            _get_data(args)

        elif args.mode == "delete":
            if not args.graph_id:
                parser.error("--graph-id required for mode=delete")
            _delete_graph(args)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
