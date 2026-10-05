# RuntimeTruth

**Verify what your AI agent is actually running.**

RuntimeTruth is an open-source runtime verification and drift-detection tool for AI agents. It is designed to compare declared, resolved, and live agent state so teams can detect unexpected changes in models, instructions, tools, MCP servers, permissions, runtime versions, and execution environment.

> Status: early private prototype. The first milestone is a local CLI and stable runtime snapshot format.

## Why

AI agents have more mutable runtime state than ordinary applications:

- model and provider routing
- system and project instructions
- tools and MCP schemas
- skills and plugins
- sandbox and network permissions
- executable/runtime versions
- environment and process identity
- repository/code state

A deployment can therefore look unchanged while the effective agent runtime has drifted.

RuntimeTruth aims to answer:

1. **What is this agent actually running right now?**
2. **What changed since the approved baseline?**
3. **Does the live runtime match policy?**
4. **Can we produce a machine-readable attestation of that state?**

## Planned CLI

```console
runtimetruth inspect <target>
runtimetruth snapshot <target>
runtimetruth diff <left> <right>
runtimetruth verify <target>
runtimetruth attest <target>
```

The CLI surface is intentionally provisional until the snapshot schema is proven against real runtimes.

## Initial scope

The first implementation targets local Linux runtimes and systemd-managed agent workers. Broader runtime adapters (containers, CI and hosted agent platforms) come after the core snapshot/diff model is stable.

See:

- [Vision](docs/vision.md)
- [Roadmap](docs/roadmap.md)
- [Architecture](docs/architecture.md)

## Development

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest
```

## License

MIT.
