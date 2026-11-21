"""Minimal Claude API client over plain HTTPS (standard library only, to keep BillSaathi free of dependencies).

Uses the Messages API with a single tool, so the answer always arrives as structured data:
    result = call_tool(key, model, system, messages, tool)   # -> dict of the tool's input
The API key is only ever sent in the x-api-key header. It is never logged and never put in an error message.
"""
import json
import time
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
DEFAULT_MODEL = "claude-opus-5-5"
# models that accept the server-side `fallbacks` parameter (a declined request is retried on another model by the API)
FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1")
MODELS = (
    ("claude-opus-5-5", "Claude Opus 5.5 (most capable, recommended)"),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5 (cheaper)"),
    ("claude-haiku-5-5", "Claude Haiku 5.5 (cheapest, simple tasks)"),
)


class LLMError(Exception):
    """A problem the owner can understand and act on. Never contains the API key."""


def _explain(status, body):
    try:
        msg = json.loads(body)["error"]["message"]
    except Exception:
        msg = ""
    if status == 401:
        return "The API key was rejected. Check it on the Integrations page."
    if status == 403:
        return "This API key is not allowed to use that model."
    if status == 404:
        return "That model was not found. Pick another model on the Integrations page."
    if status == 429:
        return "The AI service is busy or your usage limit was reached. Try again in a minute."
    if status in (500, 502, 503, 504, 529):
        return "The AI service is temporarily unavailable. Try again shortly."
    return f"The AI service refused the request ({status}): {msg[:200]}" if msg else f"The AI service returned an error ({status})."


def call_tool(api_key, model, system, messages, tool, max_tokens=4000, timeout=90, url=None, effort="low", retries=2):
    """Ask Claude to answer by calling `tool` once. Returns the tool's input as a dict."""
    if not api_key:
        raise LLMError("No API key is set. Add one on the Integrations page.")
    body = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        "tools": [dict(tool, strict=True)],
        "tool_choice": {"type": "auto"},  # forced tool choice is rejected on the newest models; the prompt asks for the tool
        "output_config": {"effort": effort},
    }
    headers = {"content-type": "application/json", "x-api-key": api_key, "anthropic-version": API_VERSION}
    if body["model"] in FALLBACK_MODELS:
        body["fallbacks"] = "default"
        headers["anthropic-beta"] = FALLBACK_BETA
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url or API_URL, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                reply = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            last = LLMError(_explain(exc.code, raw))
            if exc.code in (429, 500, 502, 503, 504, 529) and attempt < retries:
                time.sleep(min(2 ** attempt, 4))
                continue
            raise last
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = LLMError("Cannot reach the AI service. Check the internet connection.")
            if attempt < retries:
                time.sleep(min(2 ** attempt, 4))
                continue
            raise last
    else:  # pragma: no cover
        raise last or LLMError("The AI request failed.")
    if reply.get("stop_reason") == "refusal":
        raise LLMError("The AI declined this request. Enter the details by hand instead.")
    for block in reply.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == tool["name"]:
            if reply.get("stop_reason") == "max_tokens":
                raise LLMError("The AI answer was cut short. Try a shorter message.")
            if isinstance(block.get("input"), dict):
                return block["input"]
    text = " ".join(b.get("text", "") for b in reply.get("content", []) if b.get("type") == "text").strip()
    raise LLMError("The AI did not return structured details" + (f': "{text[:160]}"' if text else "."))
