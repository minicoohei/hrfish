"""OpenTelemetry initialization with Noop fallback.

Provides tracing and metrics collection for the multipath career simulator.
Works gracefully when OpenTelemetry packages are not installed by falling back
to silent Noop implementations.
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Generator

# ---------------------------------------------------------------------------
# Optional OpenTelemetry import
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import (
        SimpleSpanProcessor,
        ConsoleSpanExporter,
    )

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False


# ---------------------------------------------------------------------------
# Noop fallbacks
# ---------------------------------------------------------------------------

class _NoopSpan:
    """Span stub that silently accepts all calls."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D401
        pass

    def set_status(self, status: Any) -> None:  # noqa: D401
        pass

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class _NoopTracer:
    """Tracer stub returned when OTel is unavailable or export is disabled."""

    @contextmanager
    def start_as_current_span(
        self, name: str, **kwargs: Any
    ) -> Generator[_NoopSpan, None, None]:
        yield _NoopSpan()


# ---------------------------------------------------------------------------
# init_tracer
# ---------------------------------------------------------------------------

def init_tracer(
    session_id: str,
    export: bool = True,
    endpoint: str | None = None,
) -> Any:
    """Return an OpenTelemetry tracer or a ``_NoopTracer``.

    Parameters
    ----------
    session_id:
        Unique identifier attached as ``session.id`` resource attribute.
    export:
        If *False* (or OTel is not installed), a ``_NoopTracer`` is returned
        so that callers can use the same API without side-effects.
    endpoint:
        Optional OTLP endpoint.  When *None* a ``ConsoleSpanExporter`` is used.
    """
    if not HAS_OTEL or not export:
        return _NoopTracer()

    resource = Resource.create(
        {
            "service.name": "mirofish-simulator",
            "session.id": session_id,
        }
    )
    provider = TracerProvider(resource=resource)

    if endpoint is not None:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint)
        except ImportError:
            exporter = ConsoleSpanExporter()
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("mirofish-simulator")


# ---------------------------------------------------------------------------
# round_span context manager
# ---------------------------------------------------------------------------

@contextmanager
def round_span(
    tracer: Any, round_num: int, phase: str
) -> Generator[Any, None, None]:
    """Create an OTel span for a simulation round + phase.

    Works with both real OTel tracers and ``_NoopTracer``.
    """
    span_name = f"round-{round_num}/{phase}"
    with tracer.start_as_current_span(span_name) as span:
        span.set_attribute("round", round_num)
        span.set_attribute("phase", phase)
        yield span


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------

class MetricsCollector:
    """In-process metrics aggregation for a simulation run."""

    def __init__(self) -> None:
        self._rounds: list[dict[str, Any]] = []
        self._suggestions: dict[str, int] = defaultdict(int)
        self._token_details: list[dict[str, Any]] = []
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._zep_writes: int = 0
        self._sanitizer_blocked: int = 0

    # -- recording helpers --------------------------------------------------

    def record_round(
        self, round_num: int, phase: str, duration_s: float
    ) -> None:
        self._rounds.append(
            {"round_num": round_num, "phase": phase, "duration_s": duration_s}
        )

    def record_suggestion(self, outcome: str) -> None:
        """Record suggestion outcome: ``injected``, ``rejected``, or ``null``."""
        self._suggestions[outcome] += 1

    def record_tokens(
        self,
        model: str,
        phase: str,
        input_tok: int,
        output_tok: int,
    ) -> None:
        self._total_input_tokens += input_tok
        self._total_output_tokens += output_tok
        self._token_details.append(
            {
                "model": model,
                "phase": phase,
                "input_tok": input_tok,
                "output_tok": output_tok,
            }
        )

    def record_zep_write(self, count: int = 1) -> None:
        self._zep_writes += count

    def record_sanitizer_block(self, count: int = 1) -> None:
        self._sanitizer_blocked += count

    # -- summary ------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        total_duration = sum(r["duration_s"] for r in self._rounds)
        return {
            "rounds_completed": len(self._rounds),
            "total_duration_s": total_duration,
            "suggestions_injected": self._suggestions.get("injected", 0),
            "suggestions_rejected": self._suggestions.get("rejected", 0),
            "suggestions_null": self._suggestions.get("null", 0),
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "zep_writes": self._zep_writes,
            "sanitizer_blocked": self._sanitizer_blocked,
            "token_details": list(self._token_details),
        }
