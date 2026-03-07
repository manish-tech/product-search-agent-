import os
from typing import Optional
from langfuse import Langfuse
from langfuse.types import TraceContext


# Singleton Langfuse client
_langfuse: Optional[Langfuse] = None


def get_langfuse() -> Optional[Langfuse]:
    """Get or create the singleton Langfuse client."""
    global _langfuse

    if _langfuse is not None:
        return _langfuse

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key or public_key.endswith("...") or secret_key.endswith("..."):
        return None

    try:
        _langfuse = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host
        )
        return _langfuse
    except Exception:
        return None


class TraceWrapper:
    """Wrapper around Langfuse v3 trace context for easy span/generation tracking."""

    def __init__(self, langfuse: Langfuse, trace_context: TraceContext):
        self.langfuse = langfuse
        self.trace_context = trace_context
        self._last_span = None

    def span(self, name: str, input_data=None):
        """Start a new span under this trace."""
        try:
            span = self.langfuse.start_span(
                name=name,
                trace_context=self.trace_context,
                input=input_data
            )
            self._last_span = span
            return SpanWrapper(span)
        except Exception:
            return NoOpSpan()

    def update_output(self, output=None, error=None):
        """Update the trace with final output."""
        try:
            if self._last_span:
                kwargs = {"output": output}
                if error:
                    kwargs["status_message"] = error
                    kwargs["level"] = "ERROR"
                self._last_span.update_trace(**kwargs)
        except Exception:
            pass


class SpanWrapper:
    """Wrapper around a Langfuse span with safe generation support."""

    def __init__(self, span):
        self._span = span

    def generation(self, name, model, input=None, output=None, usage=None):
        """Log an LLM generation inside this span."""
        try:
            gen = self._span.start_observation(
                as_type="generation",
                name=name,
                model=model,
                input=input,
                output=output
            )
            if usage:
                gen.update(usage_details=usage)
            gen.end()
        except Exception:
            pass

    def end(self, output=None, status_message=None, level=None):
        """End the span with optional output."""
        try:
            if output or status_message:
                kwargs = {}
                if output:
                    kwargs["output"] = output
                if status_message:
                    kwargs["status_message"] = status_message
                if level:
                    kwargs["level"] = level
                self._span.update(**kwargs)
            self._span.end()
        except Exception:
            pass


class NoOpSpan:
    """No-op span when Langfuse fails."""
    def generation(self, *args, **kwargs): pass
    def end(self, *args, **kwargs): pass


def create_trace(session_id: str, tenant_id: str, user_message: str):
    """Create a new trace for a search request."""
    langfuse = get_langfuse()
    if langfuse is None:
        return None

    try:
        trace_id = langfuse.create_trace_id()
        ctx = TraceContext(
            trace_id=trace_id,
            session_id=session_id,
            user_id=tenant_id
        )
        return TraceWrapper(langfuse, ctx)
    except Exception:
        return None


def end_trace(trace, output: dict, error: Optional[str] = None):
    """End a trace with output data."""
    if trace is None:
        return
    try:
        trace.update_output(output=output, error=error)
    except Exception:
        pass


def flush():
    """Flush any pending Langfuse events."""
    langfuse = get_langfuse()
    if langfuse:
        try:
            langfuse.flush()
        except Exception:
            pass


def shutdown():
    """Shutdown Langfuse client gracefully."""
    global _langfuse
    if _langfuse:
        try:
            _langfuse.flush()
            _langfuse.shutdown()
        except Exception:
            pass
        _langfuse = None
