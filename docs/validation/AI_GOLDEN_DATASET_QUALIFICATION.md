# AI golden dataset qualification

## Qualified scope

`r1-ai-golden-v2` is qualified for MDARIX internal synthetic MVP assurance. It is not clinical evidence,
regulatory advice, a certified submission dataset, or production-customer validation.

The controlled suite contains VS001–VS012. Every scenario defines its investigation, required evidence,
contradictions or unknowns, prohibited conclusions, intentional anomalies, expected behavior, and four explicit
acceptance criteria. Ground truth remains under `evaluation/ground_truth` and is never included in the
application-facing canonical dataset.

## Release gates

1. `python scripts/qualify_ai_golden_dataset.py` validates structure, evidence ownership, scenario/ground-truth
   agreement, synthetic-data marking, ground-truth isolation, secret patterns, and the reviewed hash lock.
2. The normal CI workflow runs that command and tamper tests. The final release-evidence job cannot pass if the
   dataset is unqualified or changed without review.
3. Before promoting a changed provider, model, prompt, retrieval policy, or AI behavior, the separate **AI
   evaluation gate** must run the real pipeline with the contracted provider. It requires all 12 scenarios and all
   specific checks to pass with model-authored analyses.

Dataset qualification proves that the test oracle is controlled and reviewable. It does not prove that a model
passes the oracle. These are separate controls and both are required for model promotion.

## Controlled change procedure

After an approved scenario/evidence change, regenerate the dataset, review the diff, run all golden tests, and then
create a new lock:

```powershell
python data/golden/generators/generate_r1_golden_dataset.py
python scripts/qualify_ai_golden_dataset.py --approve --reviewer "<reviewer>" --change-control "<ticket>"
python scripts/qualify_ai_golden_dataset.py
python -m pytest -q tests/test_ai_golden_qualification.py tests/test_day3_golden_dataset.py tests/test_real_evaluation.py
```

Any unreviewed byte-level change to sources, scenarios, or ground truth invalidates the lock and blocks release.
