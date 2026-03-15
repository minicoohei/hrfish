"""
knowledge_search: Search curated knowledge files for prompt injection.

Usage:
    # Get relevant knowledge for an injection point
    python -m cc_layer.cli.knowledge_search \
        --candidate-context "35歳、シニアエンジニア" \
        --injection-point "top_player" \
        --max-chars 2000

    # Search knowledge by query
    python -m cc_layer.cli.knowledge_search \
        --mode search --query "AI エンジニア 転職市場"

    # Classify candidate industry
    python -m cc_layer.cli.knowledge_search \
        --mode classify --candidate-context "35歳、シニアエンジニア"

    # Check knowledge status
    python -m cc_layer.cli.knowledge_search --mode status

Output:
    JSON with knowledge text or classification result
"""
import argparse
import json
import sys

# Ensure backend is importable
import cc_layer.cli  # noqa: F401


def _get_loader():
    """Lazy import to avoid openai dependency at module level."""
    from app.services.knowledge_loader import KnowledgeLoader
    return KnowledgeLoader


def main():
    KnowledgeLoader = _get_loader()
    parser = argparse.ArgumentParser(
        description="Search curated knowledge files"
    )
    parser.add_argument(
        "--mode", choices=["inject", "search", "classify", "status"],
        default="inject",
        help="Search mode"
    )
    parser.add_argument(
        "--candidate-context",
        help="Candidate document text or context"
    )
    parser.add_argument(
        "--injection-point",
        choices=["top_player", "target_company", "hr_specialist", "group_persona"],
        help="Injection point (mode=inject)"
    )
    parser.add_argument(
        "--query",
        help="Search query (mode=search)"
    )
    parser.add_argument(
        "--category",
        choices=["industries", "job_market", "career_patterns", "all"],
        default="all",
        help="Knowledge category (mode=search)"
    )
    parser.add_argument(
        "--max-chars", type=int,
        help="Max characters to return"
    )

    args = parser.parse_args()

    try:
        if args.mode == "inject":
            if not args.candidate_context:
                parser.error("--candidate-context required for mode=inject")
            if not args.injection_point:
                parser.error("--injection-point required for mode=inject")

            text = KnowledgeLoader.get_relevant_knowledge(
                candidate_context=args.candidate_context,
                injection_point=args.injection_point,
                max_chars=args.max_chars,
            )
            result = {
                "mode": "inject",
                "injection_point": args.injection_point,
                "knowledge": text,
                "chars": len(text),
            }

        elif args.mode == "search":
            if not args.query:
                parser.error("--query required for mode=search")
            text = KnowledgeLoader.search_knowledge(
                query=args.query,
                category=args.category,
            )
            result = {
                "mode": "search",
                "query": args.query,
                "category": args.category,
                "knowledge": text,
                "chars": len(text),
            }

        elif args.mode == "classify":
            if not args.candidate_context:
                parser.error("--candidate-context required for mode=classify")
            classification = KnowledgeLoader.classify_candidate_industry(
                candidate_context=args.candidate_context
            )
            result = {
                "mode": "classify",
                "classification": classification,
            }

        elif args.mode == "status":
            status = KnowledgeLoader.get_status()
            result = {
                "mode": "status",
                **status,
            }

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
