# RuntimeTruth 0.2.4 — release candidate

Not published. This candidate combines the incomplete-verification evidence fix (#80), submodule dirty-state fidelity (#81), and the existing UTF-8/schema/time/freshness fixes on main.

Verification now requires complete evidence for selected instruction fingerprints and MCP tool catalogs. Diagnostic partial evidence remains visible but cannot establish equality. Git submodule changes remain dirty even when local ignore settings hide them. Snapshot/report schema versions are unchanged.

Run the complete suite and build/smoke-test the wheel at this candidate SHA before approving publication. Merging a pyproject.toml version change to main triggers the existing Release workflow; manual dispatch is an alternative, not a second required publication. This branch does not publish a package or create a release.
