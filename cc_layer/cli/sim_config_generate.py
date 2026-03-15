"""
sim_config_generate: Generate simulation parameters from profiles + requirements.

Usage:
    python -m cc_layer.cli.sim_config_generate \
        --graph-id mirofish_abc123 \
        --requirement "IT業界でのキャリア転換" \
        --document-text-file extracted.txt \
        --profiles-file profiles.json \
        --output-file sim_config.json

Output:
    SimulationParameters JSON
"""
import argparse
import json
import sys

# Ensure backend is importable
import cc_layer.cli  # noqa: F401


def main():
    parser = argparse.ArgumentParser(
        description="Generate simulation parameters from profiles + requirements"
    )
    parser.add_argument("--graph-id", required=True, help="Zep graph ID")
    parser.add_argument("--requirement", required=True, help="Simulation requirement")
    parser.add_argument("--document-text-file", help="Document text file")
    parser.add_argument("--profiles-file", required=True, help="Profiles JSON file")
    parser.add_argument("--simulation-id", default="sim_001", help="Simulation ID")
    parser.add_argument("--project-id", default="proj_001", help="Project ID")
    parser.add_argument("--enable-twitter", action="store_true", default=True)
    parser.add_argument("--enable-reddit", action="store_true", default=True)
    parser.add_argument("--no-twitter", action="store_true")
    parser.add_argument("--no-reddit", action="store_true")
    parser.add_argument("--output-file", help="Write output to file")

    args = parser.parse_args()

    try:
        # Read profiles
        with open(args.profiles_file, "r", encoding="utf-8") as f:
            profiles_data = json.load(f)

        # Read document text
        document_text = ""
        if args.document_text_file:
            with open(args.document_text_file, "r", encoding="utf-8") as f:
                document_text = f.read()

        # Reconstruct OasisAgentProfile objects
        from app.services.oasis_profile_generator import OasisAgentProfile
        profiles_list = profiles_data.get("profiles", profiles_data) if isinstance(profiles_data, dict) else profiles_data
        profiles = []
        for p in profiles_list:
            profiles.append(OasisAgentProfile(
                user_id=p.get("user_id", 0),
                user_name=p.get("user_name", ""),
                name=p.get("name", ""),
                bio=p.get("bio", ""),
                persona=p.get("persona", ""),
                karma=p.get("karma", 1000),
                friend_count=p.get("friend_count", 100),
                follower_count=p.get("follower_count", 150),
                statuses_count=p.get("statuses_count", 500),
                age=p.get("age"),
                gender=p.get("gender"),
                mbti=p.get("mbti"),
                country=p.get("country"),
                profession=p.get("profession"),
                interested_topics=p.get("interested_topics", []),
                source_entity_uuid=p.get("source_entity_uuid"),
                source_entity_type=p.get("source_entity_type"),
                role_category=p.get("role_category"),
            ))

        # Read entities from graph
        from app.services.zep_entity_reader import ZepEntityReader
        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(args.graph_id, enrich_with_edges=True)
        entities = filtered.entities

        # Generate config
        from app.services.simulation_config_generator import SimulationConfigGenerator
        generator = SimulationConfigGenerator()

        def progress_cb(step, total, msg):
            print(f"  [{step}/{total}] {msg}", file=sys.stderr)

        config = generator.generate_config(
            simulation_id=args.simulation_id,
            project_id=args.project_id,
            graph_id=args.graph_id,
            simulation_requirement=args.requirement,
            document_text=document_text,
            entities=entities,
            profiles=profiles,
            enable_twitter=not args.no_twitter,
            enable_reddit=not args.no_reddit,
            progress_callback=progress_cb,
        )

        # Serialize using dataclasses.asdict
        from dataclasses import asdict
        result = asdict(config)

        output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        if args.output_file:
            with open(args.output_file, "w", encoding="utf-8") as f:
                f.write(output)
            print(json.dumps({
                "status": "ok",
                "output_file": args.output_file,
            }, ensure_ascii=False))
        else:
            print(output)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
