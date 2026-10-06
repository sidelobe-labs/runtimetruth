# Data handling

RuntimeTruth is currently a local CLI. It does not operate a RuntimeTruth-hosted control plane or telemetry service.

## What stays local

RuntimeTruth does not upload snapshots or verification reports to Sidelobe.

Files are written only when the caller explicitly redirects or saves command output, for example:

```bash
runtimetruth inspect codex . --resolve-thread > baseline.json
```

The resulting file is under the caller's control. If the caller commits, uploads or forwards it, normal repository and data-handling rules apply.

## Data intentionally not serialized

Current collectors are designed not to serialize:

- environment variable values
- API keys or bearer tokens
- instruction plaintext
- raw MCP command arguments
- raw MCP resource contents
- MCP tool descriptions and schemas

RuntimeTruth may serialize metadata that can still be operationally sensitive, including:

- filesystem paths
- executable paths and versions
- Git commit identity and dirty state
- model/provider identifiers
- sandbox and approval settings
- instruction-source paths
- hashes of instruction-source files
- MCP server names, status and selected tool names
- deterministic tool-catalog fingerprints

Review snapshots before sharing them outside the environment they describe.

## Network behavior

RuntimeTruth itself has no telemetry endpoint.

Some explicit probes invoke the inspected runtime, and that runtime may perform network activity as part of normal resolution:

- `--resolve-thread` starts a local ephemeral Codex thread without starting a model turn
- `--resolve-mcp` asks Codex for thread-scoped MCP status; Codex may contact configured MCP servers or refresh authentication

RuntimeTruth does not call MCP tools during MCP status inspection.

## Future hosted features

If RuntimeTruth later gains an optional hosted component, that component must define its own data flow, retention, authentication and privacy boundary. The current local CLI should not be assumed to transmit data to such a future service.
