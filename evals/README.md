# Evaluation

Run `uv run python -m evals.run_evals --provider fake` in CI. The fixed synthetic dataset checks schema, grounding, date arithmetic, comparison grading and one real HTTP approval guard. Fixture scores describe harness behavior. Live model accuracy requires a manual live run.

`uv run python -m evals.run_evals --provider live` previews the cost estimate and exits. Set the key for the selected provider locally (`GEMINI_API_KEY` or `DEEPSEEK_API_KEY`). Add `--confirm-live` only when ready to use provider credits. The evaluator permits one bounded request per model case, has a call ceiling and checks the estimated budget before sending requests. The estimate uses standard uncached rates for the configured default model, with Gemini priced at the published post-promotional rate and DeepSeek priced at its peak rate. The default budget may require an explicit increase for the full Gemini suite. [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/) Provider charges may vary. Set an API project budget and billing alerts separately.

Live results go to ignored `evals/results/`. Cases are fictional and can be reviewed in [dataset.jsonl](dataset.jsonl). There have been no live evaluations.
