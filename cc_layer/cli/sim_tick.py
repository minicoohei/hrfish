"""
sim_tick: Execute one simulation round (tick + events + blockers).

Usage:
    python -m cc_layer.cli.sim_tick \
        --state-file cc_layer/state/session_xxx/agent_state.json \
        --agent-id agent_path_a \
        --round-num 5

Output (stdout JSON):
    {
        "events": ["昇進", ...],
        "blockers": ["育児中（子供: 2歳）", ...],
        "snapshot": {...},
        "state_updated": true
    }
"""
import argparse
import json
import os
import sys

import cc_layer.cli  # noqa: F401

from cc_layer.cli.otel_setup import init_tracer, round_span

from app.models.life_simulator import (
    BaseIdentity, CareerState, FamilyMember, ActiveBlocker, BlockerType,
    LifeEvent, LifeEventType,
)
from app.services.agent_state_store import AgentStateStore
from app.services.life_event_engine import LifeEventEngine
from app.services.blocker_engine import BlockerEngine
from app.services.persona_renderer import PersonaRenderer


def load_state_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state_file(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def reconstruct_identity(d: dict) -> BaseIdentity:
    return BaseIdentity(**d)


def reconstruct_state(d: dict) -> CareerState:
    family = [FamilyMember(**f) for f in d.get("family", [])]
    blockers = [
        ActiveBlocker(
            blocker_type=BlockerType(b["blocker_type"]),
            reason=b["reason"],
            blocked_actions=b["blocked_actions"],
            started_round=b["started_round"],
            expires_round=b.get("expires_round"),
        )
        for b in d.get("blockers", [])
    ]
    state_dict = {k: v for k, v in d.items() if k not in ("family", "blockers")}
    state = CareerState(**state_dict)
    state.family = family
    state.blockers = blockers
    return state


def main():
    parser = argparse.ArgumentParser(description="Execute one simulation round")
    parser.add_argument("--state-file", required=True, help="Path to agent_state.json")
    parser.add_argument("--agent-id", default="agent_main", help="Agent identifier")
    parser.add_argument("--round-num", type=int, required=True, help="Round number to execute")
    parser.add_argument("--scheduled-events", default=None,
                        help="JSON array of scheduled events (optional)")
    args = parser.parse_args()

    tracer = init_tracer(
        session_id=os.environ.get("MIROFISH_SESSION_ID", "default"),
        export=bool(os.environ.get("OTEL_ENABLED")),
    )

    with round_span(tracer, args.round_num, "phase_a_tick") as span:
        data = load_state_file(args.state_file)
        identity = reconstruct_identity(data["identity"])
        state = reconstruct_state(data["state"])
        seed = data.get("seed")

        # Initialize components
        state_store = AgentStateStore()
        state_store.initialize_agent(args.agent_id, identity, state)

        event_engine = LifeEventEngine(seed=seed)
        blocker_engine = BlockerEngine()
        persona_renderer = PersonaRenderer()

        # Add scheduled events if provided
        if args.scheduled_events:
            events_raw = json.loads(args.scheduled_events)
            for ev in events_raw:
                event_engine.add_scheduled_events([
                    LifeEvent(
                        event_type=LifeEventType(ev["type"]),
                        round_number=ev["round"],
                        description=ev.get("description", ""),
                        state_changes=ev.get("state_changes", {}),
                    )
                ])

        # Execute round
        current_state = state_store.tick_round(args.agent_id)
        events = event_engine.evaluate(args.agent_id, current_state)
        for event in events:
            state_store.apply_event(args.agent_id, event)

        current_state.blockers = blocker_engine.evaluate(current_state)

        # Generate persona text
        persona_text = persona_renderer.render_system_message(
            identity, current_state,
            "\n".join([f"- {e.description}" for e in events]) if events else "",
        )

        # Snapshot
        snapshot = state_store.snapshot(args.agent_id)

        # Update state file in-place
        data["state"] = current_state.to_dict()
        save_state_file(args.state_file, data)

        span.set_attribute("events_count", len(events))
        span.set_attribute("blockers_count", len(current_state.blockers))

        # Output result
        result = {
            "events": [e.description for e in events],
            "event_types": [e.event_type.value for e in events],
            "blockers": [b.reason for b in current_state.blockers],
            "persona_text": persona_text,
            "snapshot": snapshot.to_dict(),
            "state_updated": True,
        }
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
