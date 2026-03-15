"""
external_search: Search external data via Tavily API.

Usage:
    # Generic search
    python -m cc_layer.cli.external_search \
        --query "IT業界の転職市場 2025" --max-results 5

    # Job market search
    python -m cc_layer.cli.external_search \
        --mode job-market --profession "データサイエンティスト" --industry "IT"

    # Industry news
    python -m cc_layer.cli.external_search \
        --mode industry-news --industry "IT" --keywords "AI,DX"

    # HR trends
    python -m cc_layer.cli.external_search \
        --mode hr-trends --keywords "AI,リスキリング,DX"

Output:
    JSON array of search results to stdout
"""
import argparse
import json
import os
import sys

# Ensure backend is importable
import cc_layer.cli  # noqa: F401
from cc_layer.cli.sanitizer import sanitize_search_results


def _make_fetcher():
    """Create ExternalDataFetcher with env-based config."""
    # ExternalDataFetcher uses Config.TAVILY_API_KEY which reads from env.
    # We need to ensure dotenv is loaded.
    from app.services.external_data_fetcher import ExternalDataFetcher
    return ExternalDataFetcher()


def main():
    parser = argparse.ArgumentParser(
        description="External data search via Tavily API"
    )
    parser.add_argument(
        "--mode", choices=["search", "job-market", "industry-news", "hr-trends"],
        default="search",
        help="Search mode"
    )
    parser.add_argument(
        "--query",
        help="Search query (mode=search)"
    )
    parser.add_argument(
        "--profession",
        help="Profession for job market search"
    )
    parser.add_argument(
        "--industry",
        help="Industry for job-market/industry-news search"
    )
    parser.add_argument(
        "--keywords",
        help="Comma-separated keywords"
    )
    parser.add_argument(
        "--max-results", type=int, default=5,
        help="Max search results (mode=search)"
    )
    parser.add_argument(
        "--search-depth", choices=["basic", "advanced"], default="advanced",
        help="Search depth (mode=search)"
    )
    parser.add_argument(
        "--include-answer", action="store_true",
        help="Include AI-generated answer (mode=search)"
    )

    args = parser.parse_args()

    try:
        fetcher = _make_fetcher()

        if not fetcher.is_available:
            print(json.dumps({
                "error": "Tavily API not available. Set TAVILY_API_KEY environment variable.",
                "results": []
            }, ensure_ascii=False))
            sys.exit(1)

        if args.mode == "search":
            if not args.query:
                parser.error("--query required for mode=search")
            results = fetcher.search(
                query=args.query,
                search_depth=args.search_depth,
                max_results=args.max_results,
                include_answer=args.include_answer,
            )

        elif args.mode == "job-market":
            if not args.profession or not args.industry:
                parser.error("--profession and --industry required for mode=job-market")
            results = fetcher.fetch_job_market(args.profession, args.industry)

        elif args.mode == "industry-news":
            if not args.industry:
                parser.error("--industry required for mode=industry-news")
            kw = args.keywords.split(",") if args.keywords else None
            results = fetcher.fetch_industry_news(args.industry, kw)

        elif args.mode == "hr-trends":
            if not args.keywords:
                parser.error("--keywords required for mode=hr-trends")
            kw = args.keywords.split(",")
            results = fetcher.fetch_hr_trends(kw)

        if results:
            results = sanitize_search_results(results)

        output = {
            "mode": args.mode,
            "results": results,
            "count": len(results),
        }
        print(json.dumps(output, ensure_ascii=False))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
