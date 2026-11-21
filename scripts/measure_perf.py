import argparse
import json
from math import ceil
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx

from backend.app.config import Settings
from scripts.local_signup import register_from_outbox


def measure(url: str, count: int):
    identity = f"benchmark-{uuid4().hex[:8]}@example.org"
    password = uuid4().hex
    with httpx.Client(
        base_url=url, timeout=8, headers={"x-meetflow-client": "1"}
    ) as client:
        register_from_outbox(
            client, identity, password, "Local benchmark", Settings().dev_outbox
        )
        client.headers["x-csrf-token"] = client.cookies["meetflow_csrf"]
        output = {}
        try:
            for endpoint in [
                "/healthz",
                "/readyz",
                "/api/meetings",
                "/api/decisions",
                "/api/action-items",
            ]:
                samples = []
                client.get(endpoint).raise_for_status()
                for _ in range(count):
                    started = perf_counter()
                    client.get(endpoint).raise_for_status()
                    samples.append((perf_counter() - started) * 1000)
                samples.sort()
                output[endpoint] = {
                    "n": count,
                    "p50_ms": round(samples[ceil(count * 0.5) - 1], 2),
                    "p95_ms": round(samples[ceil(count * 0.95) - 1], 2),
                }
        finally:
            client.request(
                "DELETE",
                "/api/account",
                json={
                    "password": password,
                    "confirmation": "DELETE",
                },
            ).raise_for_status()
    return output


def main():
    parser = argparse.ArgumentParser(
        description="Measure sequential non-AI requests on a local server."
    )
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--count", type=int, default=25)
    parser.add_argument("--output", type=Path, default=Path("data/performance.json"))
    args = parser.parse_args()
    if not 1 <= args.count <= 35:
        parser.error("Use 1–35 samples to stay within the default API request budget.")
    if httpx.URL(args.url).host not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Benchmark a local, disposable instance only.")
    results = json.dumps(measure(args.url, args.count), indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(results + "\n", encoding="utf-8")
    print(results)


if __name__ == "__main__":
    main()
