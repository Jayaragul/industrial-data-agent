# Contributing

1. Create a focused branch from `main`.
2. Keep source data under `data/input` synthetic or non-sensitive.
3. Add or update tests for behavior changes.
4. Run `python -m pytest -q -p no:cacheprovider` with offline mode enabled.
5. Keep normal CLI output evidence-backed and concise.

Pull requests should explain the user impact, validation performed, and any safety or data-contract implications.

