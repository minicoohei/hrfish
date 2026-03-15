"""
profile_generate: Generate OASIS agent profiles from Zep graph entities.

Usage:
    # From Zep graph
    python -m cc_layer.cli.profile_generate \
        --graph-id mirofish_abc123 \
        --use-llm \
        --output-file profiles.json

    # From entity JSON file (no Zep needed)
    python -m cc_layer.cli.profile_generate \
        --entity-file entities.json \
        --output-file profiles.json

    # From graph, no LLM (rule-based profiles)
    python -m cc_layer.cli.profile_generate \
        --graph-id mirofish_abc123 \
        --no-llm \
        --output-file profiles.json

Output:
    JSON array of OasisAgentProfile objects
"""
import argparse
import json
import sys

# Ensure backend is importable
import cc_layer.cli  # noqa: F401


def _entities_from_graph(graph_id: str):
    """Read and filter entities from Zep graph."""
    from app.services.zep_entity_reader import ZepEntityReader
    reader = ZepEntityReader()
    result = reader.filter_defined_entities(graph_id, enrich_with_edges=True)
    return result.entities


def _entities_from_file(filepath: str):
    """Load entities from JSON file."""
    from app.services.zep_entity_reader import EntityNode
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    entities = []
    for item in data:
        entities.append(EntityNode(
            uuid=item.get("uuid", ""),
            name=item.get("name", ""),
            labels=item.get("labels", []),
            summary=item.get("summary", ""),
            attributes=item.get("attributes", {}),
            related_edges=item.get("related_edges", []),
            related_nodes=item.get("related_nodes", []),
        ))
    return entities


def main():
    parser = argparse.ArgumentParser(
        description="Generate OASIS agent profiles from entities"
    )
    parser.add_argument("--graph-id", help="Zep graph ID")
    parser.add_argument("--entity-file", help="Entity JSON file (alternative to --graph-id)")
    parser.add_argument(
        "--use-llm", action="store_true", default=True,
        help="Use LLM for detailed profile generation (default)"
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Rule-based profile generation (no LLM)"
    )
    parser.add_argument("--output-file", help="Write output to file")

    args = parser.parse_args()

    try:
        # Get entities
        if args.graph_id:
            entities = _entities_from_graph(args.graph_id)
        elif args.entity_file:
            entities = _entities_from_file(args.entity_file)
        else:
            parser.error("--graph-id or --entity-file required")

        if not entities:
            print(json.dumps({"profiles": [], "count": 0}, ensure_ascii=False))
            return

        print(f"Found {len(entities)} entities, generating profiles...", file=sys.stderr)

        # Generate profiles
        from app.services.oasis_profile_generator import OasisProfileGenerator
        use_llm = not args.no_llm

        generator_kwargs = {}
        if args.graph_id:
            generator_kwargs["graph_id"] = args.graph_id

        generator = OasisProfileGenerator(**generator_kwargs)

        profiles = []
        for i, entity in enumerate(entities):
            print(f"  [{i+1}/{len(entities)}] {entity.name}...", file=sys.stderr)
            profile = generator.generate_profile_from_entity(
                entity=entity,
                user_id=i + 1,
                use_llm=use_llm,
            )
            profiles.append(profile)

        # Serialize
        profiles_data = []
        for p in profiles:
            profiles_data.append({
                "user_id": p.user_id,
                "user_name": p.user_name,
                "name": p.name,
                "bio": p.bio,
                "persona": p.persona,
                "karma": p.karma,
                "friend_count": p.friend_count,
                "follower_count": p.follower_count,
                "statuses_count": p.statuses_count,
                "age": p.age,
                "gender": p.gender,
                "mbti": p.mbti,
                "country": p.country,
                "profession": p.profession,
                "interested_topics": p.interested_topics,
                "source_entity_uuid": p.source_entity_uuid,
                "source_entity_type": p.source_entity_type,
                "role_category": p.role_category,
                "created_at": p.created_at,
            })

        result = {"profiles": profiles_data, "count": len(profiles_data)}

        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output_file:
            with open(args.output_file, "w", encoding="utf-8") as f:
                f.write(output)
            print(json.dumps({
                "status": "ok",
                "output_file": args.output_file,
                "count": len(profiles_data),
            }, ensure_ascii=False))
        else:
            print(output)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
