# RuntimeTruth v0.2.4

This release preserves Git working-tree identity for paths containing trailing whitespace and improves snapshot verification input handling.

- Preserve trailing spaces, tabs and newlines in Git working-tree paths when collecting repository identity.
- Report non-UTF-8 snapshots and policy files as input errors instead of uncaught decoding exceptions.
- Require an integer snapshot schema version and a timezone-aware ISO 8601 capture timestamp.
- Add optional `--max-age SECONDS` for plain and signed verification to reject expired or future-dated current snapshots without expiring historical baselines.

Install with `pipx install runtimetruth==0.2.4` or `python -m pip install runtimetruth==0.2.4` inside a virtual environment.
