# RuntimeTruth v0.2.3

This release contains fixes to runtime comparison, Git evidence collection, and the optional signed-baseline commands.

- Report a broken or inaccessible Git repository as an inspection error instead of silently dropping its evidence.
- Treat changes between booleans and integers as drift (for example, `true` to `1`).
- Display Cosign's OIDC login instructions while signing and handle executable startup failures without a traceback.
- Keep Cosign optional for ordinary runtime verification. The signing smoke test uses Cosign v3.0.6.

The signed statement format and verification policy are unchanged.

Install with `pipx install runtimetruth==0.2.3` or `python -m pip install runtimetruth==0.2.3` inside a virtual environment.
