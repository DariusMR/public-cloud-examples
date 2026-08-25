# minimal example: instrumenting AI Endpoints with Opik
#
# cost is computed client-side - Opik can't price a custom-llm endpoint
# python examples/pull_ai_endpoints_prices.py > examples/model-prices.yaml

from dotenv import load_dotenv

load_dotenv()  # before importing opik: the SDK reads its URL at import time

import openai
import opik

from opik_ovh import enable_ingress_auth, load_prices, require, traced_completion

enable_ingress_auth()

PROJECT = require("OPIK_PROJECT_NAME")
MODEL = require("OVH_AI_ENDPOINTS_MODEL")
PRICES = load_prices()

client = openai.OpenAI(
    api_key=require("OVH_AI_ENDPOINTS_API_KEY"),
    base_url=require("OVH_AI_ENDPOINTS_BASE_URL"),
)


@opik.track(name="chat-response", project_name=PROJECT)
def answer(question: str) -> str:
    reply = traced_completion(
        client, MODEL, [{"role": "user", "content": question}], PRICES
    )

    # must be inside the function - context closes on return
    opik.opik_context.update_current_trace(
        tags=["feature:chat", "provider:ovh-ai-endpoints"],
        metadata={"session_id": "session-123", "user_id": "user-456"},
    )
    return reply


if __name__ == "__main__":
    print(answer("Explain in three sentences what LLM observability is."))
    opik.flush_tracker()  # drain the queue before the process exits
