import time
from collections.abc import Callable


MAX_RATE_LIMIT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2


def _retry_after_seconds(error: Exception, fallback: float) -> float:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return max(0.0, float(retry_after)) if retry_after is not None else fallback
    except (TypeError, ValueError):
        return fallback


def invoke_with_rate_limit_retry(
    invoke: Callable[[], str],
    *,
    max_retries: int = MAX_RATE_LIMIT_RETRIES,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
) -> str:
    """Retry temporary Mistral 429 responses with bounded exponential backoff."""
    for attempt in range(max_retries + 1):
        try:
            return invoke()
        except Exception as error:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            if status_code != 429 or attempt == max_retries:
                raise

            delay = _retry_after_seconds(error, backoff_seconds * (2**attempt))
            time.sleep(delay)

    raise RuntimeError("LLM request retry loop exited unexpectedly")