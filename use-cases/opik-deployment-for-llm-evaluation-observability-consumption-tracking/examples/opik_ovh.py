# glue between the Opik SDK and this deployment:
# ingress Basic Auth and AI Endpoints pricing, which Opik doesn't know about
#
# generate the price table first:
# python examples/pull_ai_endpoints_prices.py > examples/model-prices.yaml

import base64
import os
import pathlib
import sys

import yaml

PRICES_FILE = pathlib.Path(__file__).with_name("model-prices.yaml")


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"{name} is not set.\n"
            "Copy examples/.env.example to examples/.env and fill it in,\n"
            "or export it in your shell."
        )
    return value


def enable_ingress_auth() -> None:
    # sets the ingress Basic Auth header - skip it and traces fail with a silent 401
    from opik.hooks import HttpxClientHook, add_httpx_client_hook

    password = os.environ.get("OPIK_API_PASSWORD")
    url = os.environ.get("OPIK_URL_OVERRIDE", "")
    internal = url.startswith("http://") and (
        "localhost" in url or "127.0.0.1" in url or ".svc" in url or "opik-frontend" in url
    )

    if not password:
        if not internal:
            print(
                f"WARNING: OPIK_API_PASSWORD is not set but OPIK_URL_OVERRIDE is {url!r}.\n"
                "Traces will be rejected with 401 by the ingress, with no visible error.",
                file=sys.stderr,
            )
        return

    token = base64.b64encode(
        "{}:{}".format(os.environ.get("OPIK_API_USER", "admin"), password).encode()
    ).decode()

    # client_modifier runs after the SDK sets its own headers, so it wins
    add_httpx_client_hook(
        HttpxClientHook(
            client_modifier=lambda http_client: http_client.headers.update(
                {"Authorization": f"Basic {token}"}
            ),
            client_init_arguments=None,
        )
    )


def load_prices(path: pathlib.Path = PRICES_FILE) -> dict:
    # per-token prices, indexed by model name, id, and every alias
    if not path.exists():
        return {}

    index = {}
    for name, entry in (yaml.safe_load(path.read_text())["models"] or {}).items():
        for key in (name, entry.get("id"), *entry.get("aliases", [])):
            if key:
                index[str(key).lower()] = entry
    return index


def compute_cost(prices: dict, model: str, usage: dict | None) -> float | None:
    price = prices.get((model or "").lower())
    if usage is None or price is None:
        return None
    return usage["prompt_tokens"] * price["input"] + usage["completion_tokens"] * price["output"]


def _usage_dict(usage) -> dict:
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


def _add_usage(total: dict | None, usage: dict | None) -> dict | None:
    # sums across retries: each attempt is its own billed request, prompt included
    if total is None:
        return usage
    if usage is None:
        return total
    return {key: total[key] + usage[key] for key in total}


# reasoning models burn ~900-1100 tokens before any answer, hence the retry below
_MAX_RETRIES = 2
_HARD_CAP_TOKENS = 8000


def traced_completion(
    client, model: str, messages: list, prices: dict, max_tokens: int = 1600, **kwargs
) -> str:
    # one LLM call, traced in its own span carrying model, usage and cost
    import opik  # imported late: the SDK reads its config at import time

    @opik.track(name="llm-call", type="llm")
    def call() -> str:
        budget = max_tokens
        text = ""
        thinking_all = []
        total_usage = None

        for attempt in range(_MAX_RETRIES + 1):
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=budget,
                stream=True,
                stream_options={"include_usage": True},
                **kwargs,
            )

            parts, thinking, usage = [], [], None
            for chunk in stream:
                # usage arrives after finish_reason - don't break early
                if chunk.usage:
                    usage = _usage_dict(chunk.usage)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    parts.append(delta.content)
                # reasoning is billed too, even though it's outside `content`
                reasoning = getattr(delta, "reasoning", None) or getattr(
                    delta, "reasoning_content", None
                )
                if reasoning:
                    thinking.append(reasoning)

            text = "".join(parts)
            thinking_all.extend(thinking)
            total_usage = _add_usage(total_usage, usage)

            truncated = usage is not None and usage["completion_tokens"] >= budget
            if text or not truncated or attempt == _MAX_RETRIES:
                break
            budget = min(budget * 2, _HARD_CAP_TOKENS)

        output = {"content": text}
        if thinking_all:
            output["reasoning"] = "".join(thinking_all)

        opik.opik_context.update_current_span(
            model=model,
            provider="ovhcloud",
            usage=total_usage,
            total_cost=compute_cost(prices, model, total_usage),
            input={"messages": messages},
            output=output,
        )
        return text

    return call()
