"""
ontology_generate: Generate ontology definition from document text.

Usage:
    # Generate from text file + requirement
    python -m cc_layer.cli.ontology_generate \
        --document-text-file extracted.txt \
        --requirement "IT業界でのキャリア転換" \
        --output-file ontology.json

    # Use default ontology (no LLM call)
    python -m cc_layer.cli.ontology_generate --default \
        --output-file ontology.json

Output:
    JSON ontology definition with entity_types and edge_types
"""
import argparse
import json
import sys

# Ensure backend is importable
import cc_layer.cli  # noqa: F401


# Default ontology for when LLM is unavailable or not needed
DEFAULT_ONTOLOGY = {
    "entity_types": [
        {
            "name": "CareerAdvisor",
            "description": "Career advisor who provides career consultation and job recommendations",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name"},
                {"name": "specialty", "type": "text", "description": "Area of specialty"}
            ],
            "examples": ["転職エージェント", "キャリアカウンセラー"]
        },
        {
            "name": "HRManager",
            "description": "HR manager responsible for hiring policies and offer conditions",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name"},
                {"name": "title", "type": "text", "description": "Job title"}
            ],
            "examples": ["人事部長", "CHRO"]
        },
        {
            "name": "HiringManager",
            "description": "Hiring manager who evaluates technical skills and team fit",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name"},
                {"name": "department", "type": "text", "description": "Department"}
            ],
            "examples": ["開発部マネージャー", "チームリード"]
        },
        {
            "name": "PeerProfessional",
            "description": "Current professional in the same field for objective evaluation",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name"},
                {"name": "role", "type": "text", "description": "Current role"}
            ],
            "examples": ["同職種のエンジニア", "同業界の現役社員"]
        },
        {
            "name": "CareerCoach",
            "description": "Career coach or mentor providing guidance",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name"},
                {"name": "specialty", "type": "text", "description": "Coaching specialty"}
            ],
            "examples": ["キャリアコーチ", "メンター"]
        },
        {
            "name": "IndustryAnalyst",
            "description": "Industry analyst covering market trends and salary benchmarks",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name"},
                {"name": "focus_area", "type": "text", "description": "Focus area"}
            ],
            "examples": ["業界アナリスト", "市場調査専門家"]
        },
        {
            "name": "Company",
            "description": "A company or corporation involved in hiring",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Company name"},
                {"name": "industry", "type": "text", "description": "Industry sector"}
            ],
            "examples": ["テック企業", "コンサルティングファーム"]
        },
        {
            "name": "FormerColleague",
            "description": "Former colleague who can provide references and context",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name"},
                {"name": "relationship", "type": "text", "description": "Past relationship"}
            ],
            "examples": ["元上司", "元同僚"]
        },
        {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        },
        {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
    ],
    "edge_types": [
        {"name": "ADVISES", "description": "Provides career advice or guidance", "source_targets": [{"source": "CareerAdvisor", "target": "Person"}, {"source": "CareerCoach", "target": "Person"}], "attributes": []},
        {"name": "EVALUATES", "description": "Evaluates skills, aptitude, or fit", "source_targets": [{"source": "HiringManager", "target": "Person"}, {"source": "PeerProfessional", "target": "Person"}], "attributes": []},
        {"name": "INTERVIEWS", "description": "Conducts interview or assessment", "source_targets": [{"source": "HRManager", "target": "Person"}, {"source": "HiringManager", "target": "Person"}], "attributes": []},
        {"name": "REFERS", "description": "Provides reference or endorsement", "source_targets": [{"source": "FormerColleague", "target": "Company"}], "attributes": []},
        {"name": "WORKS_FOR", "description": "Employment or affiliation relationship", "source_targets": [{"source": "Person", "target": "Company"}, {"source": "Person", "target": "Organization"}], "attributes": []},
        {"name": "RESEARCHES", "description": "Analyzes or studies a topic or market", "source_targets": [{"source": "IndustryAnalyst", "target": "Company"}], "attributes": []},
    ],
    "analysis_summary": "デフォルトオントロジー（HRキャリアシミュレーション汎用）"
}


def main():
    parser = argparse.ArgumentParser(
        description="Generate ontology definition from document text"
    )
    parser.add_argument(
        "--document-text-file",
        help="Path to document text file"
    )
    parser.add_argument(
        "--document-text",
        help="Direct document text input"
    )
    parser.add_argument(
        "--requirement",
        help="Simulation requirement description"
    )
    parser.add_argument(
        "--additional-context",
        help="Additional context for ontology generation"
    )
    parser.add_argument(
        "--default", action="store_true",
        help="Use default ontology without LLM call"
    )
    parser.add_argument(
        "--output-file",
        help="Write output to file"
    )

    args = parser.parse_args()

    try:
        if args.default:
            result = DEFAULT_ONTOLOGY
        else:
            if not args.requirement:
                parser.error("--requirement required when not using --default")

            # Read document text
            if args.document_text_file:
                with open(args.document_text_file, "r", encoding="utf-8") as f:
                    doc_text = f.read()
            elif args.document_text:
                doc_text = args.document_text
            else:
                parser.error("--document-text-file or --document-text required")

            from app.services.ontology_generator import OntologyGenerator
            generator = OntologyGenerator()
            result = generator.generate(
                document_texts=[doc_text],
                simulation_requirement=args.requirement,
                additional_context=args.additional_context,
            )

        output = json.dumps(result, ensure_ascii=False, indent=2)

        if args.output_file:
            with open(args.output_file, "w", encoding="utf-8") as f:
                f.write(output)
            print(json.dumps({
                "status": "ok",
                "output_file": args.output_file,
                "entity_types_count": len(result.get("entity_types", [])),
                "edge_types_count": len(result.get("edge_types", [])),
            }, ensure_ascii=False))
        else:
            print(output)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
