"""
zep_search: Search Zep knowledge graph for entities, facts, and relationships.

Provides SubAgents with direct access to Zep RAG (3-layer search).

Usage:
    # Quick search (fast, semantic + BM25)
    python -m cc_layer.cli.zep_search \
        --graph-id mirofish_xxx \
        --query "候補者のキャリア経歴" \
        --mode quick

    # InsightForge (deep, multi-dimensional)
    python -m cc_layer.cli.zep_search \
        --graph-id mirofish_xxx \
        --query "この候補者のキャリア転換における最大のリスクは？" \
        --mode insight \
        --requirement "IT業界でのキャリア転換を検討"

    # Panorama (full graph snapshot)
    python -m cc_layer.cli.zep_search \
        --graph-id mirofish_xxx \
        --mode panorama

    # List entities
    python -m cc_layer.cli.zep_search \
        --graph-id mirofish_xxx \
        --mode entities

Output (stdout JSON):
    Search results with facts, nodes, edges
"""
import argparse
import json
import sys
import os

import cc_layer.cli  # noqa: F401

from app.services.zep_tools import ZepToolsService
from app.services.zep_entity_reader import ZepEntityReader


def main():
    parser = argparse.ArgumentParser(description="Search Zep knowledge graph")
    parser.add_argument("--graph-id", required=True, help="Zep graph ID")
    parser.add_argument("--query", default="", help="Search query text")
    parser.add_argument("--mode", default="quick",
                        choices=["quick", "insight", "panorama", "entities"],
                        help="Search mode")
    parser.add_argument("--requirement", default="", help="Simulation requirement (for insight mode)")
    parser.add_argument("--max-results", type=int, default=10, help="Max results for quick search")
    parser.add_argument("--entity-types", default="", help="Comma-separated entity types to filter")
    args = parser.parse_args()

    if args.mode == "entities":
        reader = ZepEntityReader()
        entity_types = [t.strip() for t in args.entity_types.split(",") if t.strip()] if args.entity_types else None
        result = reader.filter_defined_entities(
            graph_id=args.graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True,
        )
        output = {
            "mode": "entities",
            "total_count": result.total_count,
            "filtered_count": result.filtered_count,
            "entity_types": list(result.entity_types),
            "entities": [
                {
                    "uuid": e.uuid,
                    "name": e.name,
                    "labels": e.labels,
                    "summary": e.summary,
                    "attributes": e.attributes,
                    "related_edges": [
                        {"name": edge.name, "fact": edge.fact}
                        for edge in (e.related_edges or [])
                    ] if hasattr(e, 'related_edges') and e.related_edges else [],
                }
                for e in result.entities
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        return

    tools = ZepToolsService()

    if args.mode == "quick":
        if not args.query:
            print(json.dumps({"error": "quick mode requires --query"}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
        result = tools.search_graph(
            graph_id=args.graph_id,
            query=args.query,
            limit=args.max_results,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))

    elif args.mode == "insight":
        if not args.query:
            print(json.dumps({"error": "insight mode requires --query"}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
        result = tools.insight_forge(
            graph_id=args.graph_id,
            query=args.query,
            simulation_requirement=args.requirement,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))

    elif args.mode == "panorama":
        result = tools.panorama_search(graph_id=args.graph_id)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
