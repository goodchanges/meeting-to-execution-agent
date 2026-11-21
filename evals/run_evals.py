import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.ai import (
    COMPARE,
    EXTRACT,
    Comparison,
    Extraction,
    LiveProvider,
    ProviderError,
    grounded,
    wrap,
)
from backend.app.config import Settings
from backend.app.github import GitHub
from backend.app.main import create_app
from backend.app.security import CSRF
from backend.app.transcripts import deadline_for

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = "gpt-6-luna"
INPUT_USD, OUTPUT_USD = 0.10, 0.50


def compare_score(result, payload, expected):
    if len(result.relations) != 1:
        return False
    relation = result.relations[0]
    prior = payload["prior"][0]
    return (
        relation.prior_id == prior["id"]
        and relation.relation == expected["relation"]
        and grounded(relation.prior_evidence, prior["evidence_excerpt"])
        and grounded(relation.new_evidence, payload["new"]["evidence_excerpt"])
    )


def extract_score(result, payload, expected):
    if (
        len(result.action_items) != expected["tasks"]
        or len(result.decisions) != expected["decisions"]
    ):
        return False
    segments = payload["segments"]
    if any(
        not any(grounded(obj.evidence_excerpt, row["text"]) for row in segments)
        for obj in [*result.decisions, *result.action_items]
    ):
        return False
    if result.decisions and result.decisions[0].subject_key != expected["subject_key"]:
        return False
    if result.action_items:
        task = result.action_items[0]
        if task.owner != expected["owner"]:
            return False
        if task.deadline_raw and not grounded(task.deadline_raw, task.evidence_excerpt):
            return False
        resolved = deadline_for(
            task.deadline_raw, date.fromisoformat(payload["meeting_date"])
        )
        return (resolved.isoformat() if resolved else None) == expected["deadline"]
    return True


def approval_guard(expected):
    with TemporaryDirectory() as path:
        settings = Settings(
            app_env="test",
            ai_mode="demo",
            scheduler_enabled=False,
            db_path=Path(path) / "guard.sqlite",
            github_token=SecretStr(""),
        )
        app = create_app(settings)
        config = Config("alembic.ini")
        with app.state.engine.connect() as db:
            config.attributes["connection"] = db
            command.upgrade(config, "head")
        with TestClient(app) as client:
            header = {"x-meetflow-client": "1"}
            client.post(
                "/api/auth/register",
                headers=header,
                json={
                    "email": "eval@example.org",
                    "password": "synthetic-eval-password",
                    "display_name": "Eval",
                },
            ).raise_for_status()
            header["x-csrf-token"] = client.cookies[CSRF]
            calls: list[httpx.Request] = []

            def unexpected_post(request: httpx.Request):
                calls.append(request)
                return httpx.Response(500)

            app.state.github = GitHub(
                "test-only-token", httpx.MockTransport(unexpected_post)
            )
            client.patch(
                "/api/settings",
                headers=header,
                json={
                    "github_repo": "eval/fixture",
                    "timezone": "Asia/Kolkata",
                },
            ).raise_for_status()
            fixture = Path("samples/meeting1_2026-11-18.txt")
            meeting_id = (
                client.post(
                    "/api/meetings",
                    headers=header,
                    data={"title": "Eval"},
                    files={"file": (fixture.name, fixture.read_bytes(), "text/plain")},
                )
                .raise_for_status()
                .json()["id"]
            )
            result = client.post(
                f"/api/meetings/{meeting_id}/process", headers=header
            ).raise_for_status()
            if result.json()["status"] != "EXTRACTED":
                return False
            task = (
                client.get(f"/api/meetings/{meeting_id}")
                .raise_for_status()
                .json()["action_items"][0]
            )
            return (
                client.post(
                    f"/api/action-items/{task['id']}/github", headers=header
                ).status_code
                == expected["status"]
                and not calls
            )


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate fictional datasets. Live mode requires explicit confirmation."
    )
    parser.add_argument("--provider", choices=["fake", "live"], default="fake")
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--max-calls", type=int, default=24)
    parser.add_argument("--budget-usd", type=float, default=0.10)
    args = parser.parse_args()
    cases = [
        json.loads(line)
        for line in (ROOT / "dataset.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    live = None
    settings = Settings()
    output_limit = min(settings.max_output_tokens, 1200)
    if args.provider == "live":
        count = sum(case["operation"] != "guard" for case in cases)
        if settings.llm_model != DEFAULT_MODEL:
            parser.error(
                "Live evaluation currently prices only gpt-6-luna. Set LLM_MODEL accordingly."
            )
        if (
            count > args.max_calls
            or args.max_calls <= 0
            or not 0 < args.budget_usd <= 1
        ):
            parser.error(
                "Set a positive budget up to USD 1 and a call cap covering the dataset."
            )
        # Estimate with a generous prompt budget including schema overhead, and one bounded request per case.
        estimated = count * (8000 * INPUT_USD + output_limit * OUTPUT_USD) / 1_000_000
        print(
            f"Estimated upper budget for {count} paid calls: USD {estimated:.4f}",
            flush=True,
        )
        if (
            not args.confirm_live
            or not settings.llm_api_key.get_secret_value()
            or estimated > args.budget_usd
        ):
            parser.error(
                "Require --confirm-live, LLM_API_KEY and an adequate budget before sending requests."
            )
        live = LiveProvider(settings)

    results = []
    for case in cases:
        operation, expected = case["operation"], case["expect"]
        inputs = outputs = None
        error = None
        if operation == "guard":
            passed = approval_guard(expected)
        else:
            payload = case["input"]
            system, schema = (
                (COMPARE, Comparison)
                if operation == "compare"
                else (EXTRACT, Extraction)
            )
            try:
                if live:
                    raw = wrap(payload)
                    if (
                        len(raw.encode())
                        + len(json.dumps(schema.model_json_schema()).encode())
                        + len(system)
                        > 8000
                    ):
                        raise ProviderError(
                            "Evaluation prompt exceeds the conservative input budget."
                        )
                    result, usage = live.generate_structured(
                        system, raw, schema, output_limit, settings.ai_timeout
                    )
                    inputs, outputs = usage.input_tokens, usage.output_tokens
                else:
                    result = schema.model_validate(case["fixture"])
                if isinstance(result, Comparison):
                    passed = compare_score(result, payload, expected)
                else:
                    passed = extract_score(result, payload, expected)
            except ProviderError as exc:
                error = str(exc)
                passed = False
        results.append(
            {
                "id": case["id"],
                "operation": operation,
                "passed": passed,
                "input_tokens": inputs,
                "output_tokens": outputs,
                "error": error,
            }
        )
    count_passed = sum(item["passed"] for item in results)
    summary = f"{args.provider}: {count_passed}/{len(results)} passed"
    print(summary)
    if live:
        target = ROOT / "results"
        target.mkdir(exist_ok=True)
        model = re.sub(r"[^a-zA-Z0-9_.-]", "_", live.model)
        stamp = datetime.now(timezone.utc).date().isoformat()
        path = target / f"{stamp}-{model}"
        path.with_suffix(".json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
        path.with_suffix(".md").write_text(
            "# MeetFlow live evaluation\n\n" + summary + "\n", encoding="utf-8"
        )
    raise SystemExit(0 if count_passed == len(results) else 1)


if __name__ == "__main__":
    main()
