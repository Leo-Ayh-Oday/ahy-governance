# AGP: Agent Governance Protocol

Status: draft
Version: 1.0
Manifest file: `.ahy-agent.json`
Schema file: `schemas/agp.schema.json`

## Purpose

AGP, the Agent Governance Protocol, is the self-registration protocol for agents that want to be discovered and governed by Ahy Governance.

`.ahy-agent.json` is the default AGP manifest file. It is similar in spirit to `.mcp.json`, but the purpose is different:

- `.mcp.json` describes how to launch or connect MCP servers.
- AGP declares that a local project is an agent, what it can do, where it runs, and how governance should register it.

The manifest must not contain API keys, tokens, cookies, or private credentials.

## Three-Level Model

| Location | Purpose | Created by |
| --- | --- | --- |
| Agent project root `.ahy-agent.json` | Declares "I am an agent" | Developer |
| `~/.agent-registry/running/` | Runtime status such as pid, port, and heartbeat | Agent process |
| Governance database | Persisted registration and governance metadata | Ahy Governance after user approval |

## AGP Manifest Format

Minimum valid manifest:

```json
{
  "manifest_version": "1.0",
  "agent_name": "Ahy Agent",
  "framework": "ahy",
  "version": "0.1.0",
  "upstream_url": "http://localhost:8699",
  "model": "deepseek-chat",
  "capabilities": {
    "can_read": true,
    "can_search": true,
    "can_write_local": true
  },
  "registry": {
    "enabled": true,
    "heartbeat_seconds": 30
  }
}
```

Recommended full manifest:

```json
{
  "manifest_version": "1.0",
  "agent_id": "com.example.ahy-agent",
  "agent_name": "Ahy Agent",
  "framework": "ahy",
  "version": "0.1.0",
  "upstream_url": "http://localhost:8699",
  "model": "deepseek-chat",
  "description": "Local autonomous coding and research agent.",
  "capabilities": {
    "can_read": true,
    "can_search": true,
    "can_write_local": true,
    "can_execute_shell": false,
    "can_call_network": true,
    "tools": ["filesystem", "search", "browser"]
  },
  "registry": {
    "enabled": true,
    "heartbeat_seconds": 30,
    "auto_register": false
  },
  "health": {
    "url": "http://localhost:8699/health",
    "method": "GET"
  },
  "auth": {
    "type": "none"
  },
  "metadata": {
    "owner": "local",
    "tags": ["coding", "research"]
  }
}
```

## Field Rules

Required fields:

- `manifest_version`: Standard version. Current value is `1.0`.
- `agent_name`: Human-readable display name.
- `framework`: Agent framework or runtime family, such as `ahy`, `codex`, `claude-code`, `mcp`, `langchain`, `crewai`, or `custom`.
- `version`: Agent version.
- `upstream_url`: Local or remote URL used by governance to probe the agent.
- `model`: Default model name or `unknown`.
- `capabilities`: Declared capability flags.
- `registry`: Registration preferences.

Recommended fields:

- `agent_id`: Stable reverse-DNS or slug identifier. This is safer than deduplicating by display name.
- `description`: Short human-readable description.
- `health`: Optional health probe endpoint.
- `auth`: Authentication mode only. Do not store secrets here.
- `metadata`: Owner, tags, or other non-secret information.

## Capability Semantics

Capability flags are declarations, not permissions by themselves. Ahy Governance should still enforce policy after registration.

Core flags:

- `can_read`: Can read local or remote content.
- `can_search`: Can search files, memory, web, or indexes.
- `can_write_local`: Can write to local files.
- `can_execute_shell`: Can execute shell commands.
- `can_call_network`: Can make outbound network requests.

Optional `tools` should be a short list of tool families, not raw credentials or command lines.

## Runtime Status

When an agent starts, it may write runtime state under:

```text
~/.agent-registry/running/{agent_id}.json
```

Runtime file example:

```json
{
  "agent_id": "com.example.ahy-agent",
  "agent_name": "Ahy Agent",
  "manifest_path": "C:/Users/example/agent/.ahy-agent.json",
  "pid": 12345,
  "port": 8699,
  "started_at": "2026-06-02T12:00:00+08:00",
  "heartbeat_at": "2026-06-02T12:00:30+08:00",
  "status": "running"
}
```

Runtime files are hints. Governance should tolerate stale runtime files and verify the agent with a health probe before registration.

## Discovery Algorithm

Agent Discovery should use this order:

1. Search configured roots for `.ahy-agent.json`.
2. Parse JSON and validate against `schemas/agp.schema.json`.
3. Reject manifests with secrets or invalid `upstream_url`.
4. Read matching runtime state from `~/.agent-registry/running/` when present.
5. Probe `health.url` if defined, otherwise probe `upstream_url`.
6. Show candidates to the user with source path, status, framework, model, and capabilities.
7. Persist selected agents to the Governance database.

Discovery must not auto-register agents unless the manifest sets `registry.auto_register=true` and the current workspace policy explicitly allows it.

## Security Rules

- Never store secrets in `.ahy-agent.json`.
- Do not execute commands from the manifest.
- Do not trust capability declarations as permission grants.
- Do not scan the entire disk by default. Use configured roots such as the user's project directories, home-level agent directories, and explicit workspace paths.
- Treat `upstream_url` as untrusted until probed.
- Require user approval before first persistent registration.

## Database Registration

After user approval, Ahy Governance should persist:

- manifest identity: `agent_id`, `agent_name`, `framework`, `version`
- connection info: `upstream_url`, `health.url`, `auth.type`
- capability declaration
- runtime status snapshot
- registration source path
- workspace id
- timestamps for registration and last probe

The database is the source of truth after registration. The manifest remains the source of truth for local discovery.

## Compatibility

Future versions should preserve backward compatibility for all required `1.0` fields. Breaking changes require a new `manifest_version`.

Unknown fields should be ignored by default and preserved only when the database has an extension metadata column.
