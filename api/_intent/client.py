"""
OpenAI Chat Completions over the standard library.

No SDK: requirements.txt stays empty, so there is nothing to install and nothing
that can break on a runtime bump. urllib is enough for one POST.

This module is the ONLY thing in the intent layer that knows a provider exists.
Flagging, validation, the fourth reading and the spelling profile all sit behind
`call()` and would not change if the provider did.

CONFIGURATION IS ALL ENVIRONMENT, AND ALL OPTIONAL.
  OPENAI_API_KEY      absent -> the intent reading is omitted and the app runs
                      exactly as it does today. Never an error.
  INTENT_MODEL        model id, recorded in every response so a score can be
                      traced to the model that produced it.
                        gpt-5.6-sol    frontier, most accurate, dearest
                        gpt-5.6-terra  balanced -- the default
                        gpt-5.6-luna   ~80% cheaper, for large batches
  INTENT_EFFORT       none | low | medium | high | xhigh        (default low)
  INTENT_TIMEOUT      seconds per request                       (default 45)
  INTENT_CONCURRENCY  requests in flight                        (default 8)
  INTENT_DEADLINE     seconds for a whole batch                 (default 240)

WHY THERE IS NO TEMPERATURE. The brief asked for temperature 0. These models
reject it outright -- verified against the live API, not assumed:

    HTTP 400  Unsupported value: 'temperature' does not support 0 with this
              model. Only the default (1) value is supported.

Temperature 0 also never guaranteed identical output on the models that did
accept it. Reproducibility here comes from the per-script cache (a re-run of the
same script under the same model replays the same mapping and is not re-billed)
and from recording the model id alongside every score, which is what an
assessment tool actually needs in order to defend a mark.
"""

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.6-terra"
EFFORTS = ("none", "low", "medium", "high", "xhigh")

# Retryable per the API's own guidance: rate limit, server error, overloaded.
_RETRY_STATUS = {408, 409, 429, 500, 502, 503, 529}
_MAX_ATTEMPTS = 3


def _env(name, default):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def config():
    """Everything the layer needs to describe itself, key excluded."""
    effort = _env("INTENT_EFFORT", "low")
    return {
        "model": _env("INTENT_MODEL", DEFAULT_MODEL),
        "effort": effort if effort in EFFORTS else "low",
        "timeout": float(_env("INTENT_TIMEOUT", "45")),
        "concurrency": int(_env("INTENT_CONCURRENCY", "8")),
        "deadline": float(_env("INTENT_DEADLINE", "240")),
    }


def available():
    """False means: run the deterministic app, omit the intent reading."""
    return bool(os.environ.get("OPENAI_API_KEY"))


class IntentUnavailable(Exception):
    """Raised inside a worker; always caught and turned into a note."""


def _post(payload, timeout, key):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def call(system, user_text, schema, cfg, deadline_at):
    """
    One request. Returns the parsed object the schema describes.

    `response_format` in strict json_schema mode constrains the reply at the API
    layer, so there is no prose to parse and no "the model wrapped it in a code
    fence" case to defend against.
    """
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise IntentUnavailable("no OPENAI_API_KEY")

    payload = {
        "model": cfg["model"],
        # Not `max_tokens`: these models reject the legacy name with a 400.
        "max_completion_tokens": 4096,
        "reasoning_effort": cfg["effort"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "verdicts", "strict": True,
                            "schema": schema},
        },
    }

    last = None
    for attempt in range(_MAX_ATTEMPTS):
        if time.time() >= deadline_at:
            raise IntentUnavailable("batch deadline reached")
        remaining = max(1.0, min(cfg["timeout"], deadline_at - time.time()))
        try:
            data = _post(payload, remaining, key)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            last = "HTTP %s %s" % (exc.code, detail)
            if exc.code not in _RETRY_STATUS:
                # 400/401/403/404 are configuration faults. Retrying an
                # unsupported parameter or a bad key just burns the deadline.
                raise IntentUnavailable(last)
            wait = float(exc.headers.get("retry-after") or (2 ** attempt))
        except Exception as exc:
            last = "%s: %s" % (type(exc).__name__, exc)
            wait = 2 ** attempt
        else:
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            # A safety decline arrives as a 200 with `refusal` set, so it has to
            # be read before the content is touched.
            if msg.get("refusal"):
                raise IntentUnavailable("model declined: %s"
                                        % str(msg["refusal"])[:120])
            if choice.get("finish_reason") == "length":
                raise IntentUnavailable("reply hit the output cap")
            text = msg.get("content") or ""
            if not text.strip():
                raise IntentUnavailable("empty response")
            try:
                return json.loads(text)
            except ValueError as exc:
                raise IntentUnavailable("unparseable response: %s" % exc)
        if time.time() + wait >= deadline_at:
            break
        time.sleep(wait)
    raise IntentUnavailable(last or "request failed")


def fan_out(jobs, cfg):
    """
    Run one request per script, concurrently, inside one shared deadline.

    A job is (key, thunk). Every result is (key, value, error) -- a failed job
    never propagates, because a batch of 100 must still return the
    deterministic answer for the other 99.
    """
    deadline_at = time.time() + cfg["deadline"]
    out = []

    def run(item):
        k, thunk = item
        try:
            return k, thunk(deadline_at), None
        except IntentUnavailable as exc:
            return k, None, str(exc)
        except Exception as exc:                       # never kill the batch
            return k, None, "%s: %s" % (type(exc).__name__, exc)

    if not jobs:
        return out
    workers = max(1, min(cfg["concurrency"], len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for res in pool.map(run, jobs):
            out.append(res)
    return out
