# Origin

RuntimeTruth started with a fairly boring operational question:

> **What is this agent actually running right now?**

The question came up while working with self-hosted CI and long-running Linux workers. The repository could say one thing, deployment configuration could say another, and neither necessarily proved the state of the process that was actually live.

That gap becomes more important for AI agents. Their effective runtime is not defined by source code alone. Model routing, instructions, tools, MCP servers, permissions, environment, runtime versions, and local code state can all change behaviour without producing an obvious application-code diff.

The first idea was not to build another monitoring dashboard. It was to make the runtime state inspectable as evidence.

## Building from evidence outward

The project deliberately started at the bottom of the stack.

The first working collector inspected a real systemd-managed worker and recorded a small allowlist of live service state. The next step added local Git identity. Those pieces were then composed through procfs:

```text
systemd unit
    |
    v
live process
    |
    +--> executable
    +--> working directory
            |
            v
       Git repository
            |
            +--> HEAD commit
            +--> branch
            +--> clean / dirty state
```

That path was validated against an actual self-hosted GitHub Actions runner and a controlled transient systemd service, rather than designed entirely from fixtures.

This sequence shaped one of RuntimeTruth's main design rules: **evidence before inference**.

A collector should say what it observed, how it observed it, and where the boundary of that observation ends. For example, finding a Git checkout at a process working directory is useful evidence about the runtime context; it is not proof that the Git commit cryptographically identifies the executable.

## Why the name

The name **RuntimeTruth** is intentionally literal.

The tool should not merely repeat what configuration says *ought* to be running. It should make it possible to inspect what can actually be established about the live runtime, compare that state over time, and eventually verify it against an explicit policy.

Where RuntimeTruth cannot prove something, the goal is to represent that uncertainty rather than quietly turn it into an assumption.

## Where it goes from here

The early work is intentionally local-first and unglamorous: stable snapshots, provenance, semantic diffs, and a small set of well-understood collectors.

Agent-specific adapters, policy verification, attestations, and any hosted product come later. The core has to be useful and trustworthy on one machine first.
