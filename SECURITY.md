# Security Policy

RuntimeTruth inspects agent runtime state and may operate near sensitive configuration. Security reports are therefore treated as private disclosures.

## Supported versions

RuntimeTruth is currently pre-release. Until the first tagged stable release, security fixes are made on the latest `main` branch only.

## Reporting a vulnerability

Do not include vulnerability details, secrets, tokens, private runtime snapshots or private infrastructure information in a public issue.

When GitHub private vulnerability reporting is available for this repository, use **Security → Report a vulnerability**.

If private vulnerability reporting is unavailable, open a minimal public issue asking the maintainers for a private reporting channel. Do not include exploit details in that issue.

## Sensitive data

A useful report should contain the minimum evidence needed to reproduce the problem. Redact or replace:

- authentication tokens and API keys
- environment variable values
- private instruction or prompt contents
- private repository contents
- internal hostnames, addresses and paths when they are not necessary to reproduce the issue

## Scope

Security reports are especially useful for issues involving:

- accidental secret or instruction-content capture
- unsafe parsing of untrusted runtime data
- command or argument injection
- incorrect evidence provenance that could cause a false verification PASS
- bypasses of protected runtime invariants
- unsafe MCP probing or unexpected tool execution
- package or CI supply-chain issues

RuntimeTruth does not currently provide a cryptographic trust guarantee for baseline files. A caller-selected baseline can be modified unless the caller protects it through separate repository or artifact controls.
