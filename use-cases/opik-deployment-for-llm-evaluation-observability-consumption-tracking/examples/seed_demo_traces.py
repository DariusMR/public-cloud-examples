# seed demo traces across teams, users and load profiles
# python examples/seed_demo_traces.py                # real calls
# python examples/seed_demo_traces.py --dry-run      # print the plan, no calls
# python examples/seed_demo_traces.py --turns 3      # 3 exchanges per user
#
# no user field in Opik, so per-user tracking rides on tags + thread_id

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()  # before importing opik: the SDK reads its URL at import time

import openai
import opik

from opik_ovh import enable_ingress_auth, load_prices, require, traced_completion

enable_ingress_auth()


# keep these names stable across runs, or you multiply projects instead of filling them
TEAMS = {
    "marketing": {
        "users": ["claire.d", "marc.l"],
        "tags": ["team:marketing", "feature:copywriting"],
        "prompts": [
            "Write three headlines for a managed Kubernetes product page.",
            "Summarise in two sentences why LLM observability matters to a marketing director.",
            "Suggest five keywords for an article about inference cost tracking.",
        ],
    },
    "frontend-dev": {
        "users": ["nadia.b", "tom.g"],
        "tags": ["team:frontend", "feature:code-assist"],
        "prompts": [
            "Explain in three points when to use useMemo rather than useCallback in React.",
            "Write a React component that renders an accessible loading state.",
            "Which performance pitfalls should I watch for in a virtualised list?",
        ],
    },
    "backend-dev": {
        "users": ["yann.m"],
        "tags": ["team:backend", "feature:code-assist"],
        "prompts": [
            "Compare a Redis queue and a Kafka queue for trace ingestion.",
            "How do I prevent concurrent Liquibase migrations across several replicas?",
            "Explain what a ReplacingMergeTree engine is useful for in ClickHouse.",
        ],
    },
    "content-writing": {
        "users": ["ines.r", "paul.m", "sofia.a"],
        "tags": ["team:content", "feature:redaction"],
        "prompts": [
            "Write the introduction of a Kubernetes deployment guide, professional tone.",
            "Rewrite this sentence to be more direct: 'It is possible that the service may be interrupted.'",
            "Propose a five-part outline for an article about controlling LLM costs.",
        ],
    },
    "customer-support": {
        "users": ["leila.h", "bruno.f"],
        "tags": ["team:support", "feature:triage"],
        "prompts": [
            "A customer reports missing traces while their application raises no error. What should we check?",
            "Explain to a customer, simply, the difference between block storage and object storage.",
            "Write a short reply to a customer whose TLS certificate has expired.",
        ],
    },
}

# long enough that input dominates the cost, no external file needed
LOG_EXCERPT = (
    "2026-08-04T09:14:22Z backend INFO  batch accepted traces=48 spans=96 latency_ms=131\n"
    "2026-08-04T09:14:23Z backend WARN  clickhouse insert retried attempt=2 reason=timeout\n"
    "2026-08-04T09:14:25Z python-backend WARN  redis client initialisation deferred\n"
    "2026-08-04T09:14:31Z backend INFO  migration checksum verified changesets=98\n"
    "2026-08-04T09:14:40Z frontend INFO  GET /api/v1/private/projects 200 duration_ms=23\n"
)

# (context repeats, token budget) - not guaranteed, traced_completion doubles the budget on retry
WORKLOADS = {
    "short": (0, 1600),
    "intensive-input": (40, 3200),
    "intensive-output": (0, 2400),
}

MODEL = require("OVH_AI_ENDPOINTS_MODEL")
PRICES = load_prices()
CLIENT = openai.OpenAI(
    api_key=require("OVH_AI_ENDPOINTS_API_KEY"),
    base_url=require("OVH_AI_ENDPOINTS_BASE_URL"),
)


def build_messages(prompt: str, repeats: int) -> list[dict]:
    if not repeats:
        return [{"role": "user", "content": prompt}]
    context = LOG_EXCERPT * repeats
    return [
        {
            "role": "user",
            "content": (
                "Here is an extract of platform logs:\n\n"
                f"{context}\n"
                f"Using only this extract, answer concisely: {prompt}"
            ),
        }
    ]


def build_runner(project: str, tags: list[str]):
    # project_name goes on the decorator, or spans land in "Default Project"
    @opik.track(name="chat-response", project_name=project)
    def run(prompt: str, user: str, thread: str, workload: str) -> str:
        repeats, max_tokens = WORKLOADS[workload]
        reply = traced_completion(
            CLIENT, MODEL, build_messages(prompt, repeats), PRICES,
            max_tokens=max_tokens,
        )

        # user goes in a tag for lack of a real field; thread_id feeds the Threads view
        opik.opik_context.update_current_trace(
            thread_id=thread,
            tags=[*tags, f"user:{user}", f"workload:{workload}"],
            metadata={"user_id": user, "workload": workload, "model": MODEL},
        )
        return reply

    return run


def plan(turns: int):
    # profile rotates with the index so every user hits all three by --turns 3
    kinds = list(WORKLOADS)
    for project, team in TEAMS.items():
        for user in team["users"]:
            for index in range(turns):
                prompt = team["prompts"][index % len(team["prompts"])]
                workload = kinds[index % len(kinds)]
                thread = f"{project}-{user.split('.')[0]}"
                yield project, team["tags"], user, thread, workload, prompt


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo traces across teams, users and load profiles.")
    parser.add_argument("--turns", type=int, default=3,
                        help="exchanges per user (default: 3, one per profile)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan without calling the model")
    args = parser.parse_args()

    calls = list(plan(args.turns))
    users = sum(len(t["users"]) for t in TEAMS.values())
    print(f"{len(TEAMS)} projects, {users} users, {len(WORKLOADS)} profiles, "
          f"{len(calls)} traces to produce.", file=sys.stderr)

    if args.dry_run:
        for project, _, user, _, workload, prompt in calls:
            print(f"  {project:16} {user:16} {workload:16} {prompt[:44]}…", file=sys.stderr)
        return 0

    runners, failures = {}, 0
    for project, tags, user, thread, workload, prompt in calls:
        if project not in runners:
            runners[project] = build_runner(project, tags)
        try:
            runners[project](prompt, user, thread, workload)
            print(f"  ok    {project:16} {user:16} {workload}", file=sys.stderr)
        except Exception as error:  # one failing team doesn't stop the others
            failures += 1
            print(f"  FAIL  {project:16} {user:16} {workload}: "
                  f"{type(error).__name__}: {error}", file=sys.stderr)

    opik.flush_tracker()  # drain the queue before the process exits
    print(f"done: {len(calls) - failures}/{len(calls)} traces sent.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
