# Evaluation

Run `uv run python -m evals.run_evals --provider fake` in CI. The fixed synthetic dataset checks schema, grounding, date arithmetic, comparison grading and one real HTTP approval guard. Fixture scores describe harness behavior. Live model accuracy requires a manual live run.

`uv run python -m evals.run_evals --provider live` previews the cost estimate and exits. Add `--confirm-live` only when ready to use provider credits. The evaluator permits one bounded request per model case, has a call ceiling and checks the estimated budget before sending requests. The default rates reflect the [GPT-6 Luna model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna). Provider charges may vary. Set an API project budget and billing alerts separately.

Live results go to ignored `evals/results/`. Cases are fictional and can be reviewed in [dataset.jsonl](dataset.jsonl). There have been no live evaluations.
