"""Single choke-point for every model call. LIVE ONLY.

There is no offline mode. The agent requires a working ANTHROPIC_API_KEY.
If the key is missing, invalid, or out of credits, calls raise LLMError with
a friendly message that the UI surfaces as a popup.

Model routing:
  cheap    -> claude-haiku-4-5-20251001   (plan, critique, summarize)
  capable  -> claude-sonnet-4-6           (SQL drafting)
  strong   -> claude-opus-4-8             (escalate on repeated failure)
"""
from __future__ import annotations

import os

CHEAP = "claude-haiku-4-5-20251001"
CAPABLE = "claude-sonnet-4-6"
STRONG = "claude-opus-4-8"

CONTACT = "srujan.nalam@gmail.com"

try:
    import anthropic
except ImportError:
    anthropic = None


class LLMError(Exception):
    """Raised when a model call can't be made. Carries a user-facing message."""
    def __init__(self, kind: str, user_message: str):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message
        self.contact = CONTACT


def _classify(exc: Exception) -> LLMError:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if any(w in msg for w in ("credit", "billing", "quota", "insufficient", "balance")):
        return LLMError("credits",
            f"The API credits have run out. Please contact {CONTACT} to top up API credits.")
    if "authentication" in name or "permission" in name or "401" in msg \
            or "invalid x-api-key" in msg or "invalid api key" in msg or "api key" in msg:
        return LLMError("auth",
            f"The API key is invalid or expired. Please contact {CONTACT} to restore access.")
    if "ratelimit" in name or "429" in msg or "rate limit" in msg or "overloaded" in msg:
        return LLMError("rate",
            "The service is rate-limited right now. Please wait a few seconds and try again.")
    return LLMError("other",
        f"The model request failed ({type(exc).__name__}). If this keeps happening, contact {CONTACT}.")


class LLM:
    def __init__(self) -> None:
        self.tokens_used = 0
        self._client = None
        key = os.environ.get("ANTHROPIC_API_KEY")
        if key and anthropic is not None:
            try:
                self._client = anthropic.Anthropic(api_key=key)
            except Exception:
                self._client = None

    @property
    def live(self) -> bool:
        return self._client is not None

    def complete(self, system: str, prompt: str, model: str = CAPABLE,
                 max_tokens: int = 1024, task=None, ctx=None) -> str:
        if not self.live:
            raise LLMError("no_key",
                f"The agent isn't configured with an API key. Please contact {CONTACT}.")
        try:
            msg = self._client.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise _classify(exc) from exc
        self.tokens_used += msg.usage.input_tokens + msg.usage.output_tokens
        return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
