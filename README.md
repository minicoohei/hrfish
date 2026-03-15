# MiroFish

AI Career Simulator powered by Claude Code SubAgents.

Simulate 10-year career trajectories with multi-path analysis, social sentiment simulation, and detailed HTML reports.

## Features

- **Multi-Path Career Simulation** - Generate 5 parallel career paths with best/likely/base/worst scenarios
- **SNS Agent Swarm** - 50-character social simulation discussing career decisions
- **Fact Checking** - Verify salary/market claims against real data (via Tavily)
- **Macro Trend Analysis** - Incorporate industry trends and labor market data
- **Interactive HTML Reports** - Rich visualizations with income charts, scenario comparisons, and agent discussions

## Requirements

- Python 3.11+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (for SubAgent orchestration)

## Installation

```bash
pip install -e .

# Optional dependencies
pip install -e ".[zep]"      # Zep knowledge graph
pip install -e ".[search]"   # Tavily web search
pip install -e ".[otel]"     # OpenTelemetry tracing
pip install -e ".[all]"      # Everything
```

## Quick Start

### Demo Mode (no API keys needed)

Generate a report from bundled sample data:

```bash
python -m cc_layer.cli.pipeline_run \
  --session-dir cc_layer/fixtures/samples/session_01 \
  --phase report
```

### Full Pipeline

Check pipeline status and follow guided steps:

```bash
python -m cc_layer.cli.pipeline_run \
  --session-dir cc_layer/state/my_session \
  --phase status
```

The orchestrator guide at `cc_layer/prompts/orchestrator.md` provides step-by-step instructions for running the complete pipeline with Claude Code.

## Architecture

```
cc_layer/
  app/
    models/          # Pydantic domain models (CareerState, BaseIdentity, etc.)
    services/        # Business logic (event engine, blocker engine, etc.)
    utils/           # Shared utilities (logging, retry, validation)
  cli/               # CLI tools (sim_init, sim_tick, path_score, report_html, etc.)
  schemas/           # Data contracts (canonical models, normalizer, validator)
  prompts/           # SubAgent prompt templates
  fixtures/          # Sample session data for testing
  tests/             # Test suite
```

### Pipeline Phases

| Phase | Tool | Description |
|-------|------|-------------|
| 0 | `sim_init` | Initialize candidate profile and career state |
| 1a | SubAgent | Design 5 career paths (PathDesignerAgent) |
| 1b | SubAgent x5 | Expand each path into 10-year scenarios (PathExpanderAgent) |
| 2 | `path_score` | Score and rank paths |
| 3 | `generate_swarm_agents` | Create SNS agent profiles |
| 4 | SubAgent | Run 40-round swarm discussion |
| 5-6 | `fact_check` | Extract and verify claims |
| 7 | SubAgent | Analyze macro trends |
| 8 | `pipeline_run --phase report` | Generate HTML report |

## CLI Reference

All CLIs are self-documenting:

```bash
python -m cc_layer.cli.sim_init --help
python -m cc_layer.cli.path_score --help
python -m cc_layer.cli.report_html --help
python -m cc_layer.cli.pipeline_run --help
```

## Testing

```bash
python -m pytest cc_layer/tests/ -v
```

## License

MIT
