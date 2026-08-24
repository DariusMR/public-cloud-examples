# pull the AI Endpoints catalog and build a per-model price table
# python examples/pull_ai_endpoints_prices.py > examples/model-prices.yaml
#
# catalog prices per million tokens; output converts to per-token

import sys
import requests
import yaml

CATALOG_URL = "https://catalog.endpoints.ai.ovh.net/rest/v1/models_v2"
UNITS = {"million_input_tokens": "input", "million_output_tokens": "output"}


def main() -> int:
    catalog = requests.get(CATALOG_URL, timeout=30).json()

    models = {}
    for model in catalog:
        metadata = model.get("metadata") or {}
        pricing = (metadata.get("usage_information") or {}).get("pricing") or []

        prices = {
            UNITS[entry["price_unit"]]: entry["price"] / 1_000_000
            for entry in pricing
            if entry.get("price_unit") in UNITS
        }
        if not prices:
            continue

        models[model["name"]] = {
            "id": model["id"],
            "aliases": metadata.get("aliases", []),
            "currency": "EUR",
            **prices,
        }

    if not models:
        print("no priced model found in the catalogue", file=sys.stderr)
        return 1

    yaml.safe_dump(
        {"provider": "ovh-ai-endpoints", "models": models},
        sys.stdout,
        sort_keys=True,
        allow_unicode=True,
    )
    print(f"{len(models)} priced models", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
