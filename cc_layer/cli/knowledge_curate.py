"""
knowledge_curate: Curate industry knowledge via Tavily + LLM pipeline.

Usage:
    python -m cc_layer.cli.knowledge_curate \
        --ontology-file ontology.json \
        --candidate-context "35歳、シニアエンジニア、IT業界10年" \
        --graph-id mirofish_abc123 \
        --output-dir cc_layer/state/session_xxx/knowledge/

Output:
    JSON with classification, curated_files list, and stats
"""
import argparse
import json
import sys

# Ensure backend is importable
import cc_layer.cli  # noqa: F401
from cc_layer.cli.sanitizer import sanitize_text


def main():
    parser = argparse.ArgumentParser(
        description="Curate industry knowledge via Tavily + LLM"
    )
    parser.add_argument(
        "--ontology-file",
        help="Ontology JSON file (entity_types used for classification)"
    )
    parser.add_argument(
        "--candidate-context",
        help="Candidate context text"
    )
    parser.add_argument(
        "--candidate-context-file",
        help="File containing candidate context"
    )
    parser.add_argument(
        "--graph-id", default="",
        help="Zep graph ID (for logging)"
    )
    parser.add_argument(
        "--output-dir",
        help="Override output directory (default: preset_knowledge/)"
    )

    args = parser.parse_args()

    try:
        from app.services.knowledge_curator import KnowledgeCurator

        # Read ontology entities
        ontology_entities = []
        if args.ontology_file:
            with open(args.ontology_file, "r", encoding="utf-8") as f:
                ontology = json.load(f)
            ontology_entities = ontology.get("entity_types", [])

        # Read candidate context
        candidate_context = ""
        if args.candidate_context:
            candidate_context = args.candidate_context
        elif args.candidate_context_file:
            with open(args.candidate_context_file, "r", encoding="utf-8") as f:
                candidate_context = f.read()

        # Sanitize raw content before LLM processing
        candidate_context = sanitize_text(candidate_context, max_length=2000)

        curator = KnowledgeCurator()

        # Override output directory if specified
        if args.output_dir:
            import os
            os.makedirs(args.output_dir, exist_ok=True)
            curator.knowledge_dir = args.output_dir

        result = curator.curate_for_ontology(
            ontology_entities=ontology_entities,
            candidate_context=candidate_context,
            graph_id=args.graph_id,
        )

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
