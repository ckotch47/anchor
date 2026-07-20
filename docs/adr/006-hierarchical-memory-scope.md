# ADR-006: Hierarchical memory with global and project scopes

- Status: accepted
- Date: 2026-07-20

## Context

Anchor already stores canonical notes, tasks, history, and files with explicit
project scope. Memory is a retrieval read model over those records, not a new
source of truth.

Different chats may belong to the same user but different projects. The agent
should be able to reuse stable user-level knowledge across chats without
leaking project-specific context into another project.

TencentDB-Agent-Memory provides a useful pattern: compact derived memories,
progressive disclosure, and explicit drill-down to the original evidence. We
will adopt those ideas without coupling Anchor to OpenClaw, Hermes, or a
separate gateway runtime.

## Decision

Add hierarchical memory as a rebuildable projection over existing canonical
records.

### Scope hierarchy

Each memory fact has one visibility scope:

- `chat` — valid only for one conversation/session;
- `project` — reusable inside one project;
- `global` — reusable across the user's projects and chats.

The source project and source chat remain provenance metadata even when a fact
is promoted to `global`.

Default recall is:

```text
global facts + current project facts + current chat facts
```

Cross-project recall is explicit. A global fact is not a copy of every project
record: only facts that pass promotion rules may enter the global scope.

### Memory layers

- **L0** — canonical history, notes, tasks, files, and raw evidence;
- **L1** — atomic facts extracted from L0;
- **L2** — scenario summaries grouped from related L1 facts;
- **L3** — persona or reusable skill summaries, deferred until L1/L2 quality is
  proven.

L1 is the first implementation target. L2 and L3 are optional derived layers,
not prerequisites for the initial memory contract.

### `memory_facts` logical contract

The future table/projection must contain at least:

- `id` — UUIDv7;
- `project` — source project, nullable only for truly global user facts;
- `scope` — `chat`, `project`, or `global`;
- `source_chat_id` — originating conversation/session identifier;
- `fact_type` — preference, rule, decision, identity, workflow, or other
  configured type;
- `content` — compact human/agent-readable fact;
- `confidence` — normalized score;
- `status` — `candidate`, `active`, `superseded`, `conflicted`, or `deleted`;
- `evidence_refs` — typed references to canonical document/chunk ids;
- `valid_from` / `valid_until` — temporal validity;
- `supersedes_id` — prior fact when a fact replaces it;
- `created_at` / `updated_at`.

Summaries and facts are derived and must be rebuildable from canonical rows and
their evidence references.

## Promotion rules

Facts start as `candidate` and may become `active` only after validation.

Promotion to `global` requires one of:

1. explicit user/agent instruction such as `remember globally`;
2. repeated evidence across chats/projects plus a policy check;
3. a configured rule for stable user preferences with sufficient confidence.

The following remain project-scoped by default:

- project architecture and implementation decisions;
- paths, credentials, private identifiers, and operational details;
- temporary tasks and incidents;
- facts whose meaning conflicts across projects.

Conflicting facts are retained with provenance. They are not silently
overwritten. A project-specific fact may override a global preference during
project recall without mutating the global fact.

## Retrieval contract

The future `memory search` and `memory recall` contracts should support:

- `scope`: `chat`, `project`, `global`, or `all`;
- `project`: one or more explicit project filters;
- `chat_id`: optional conversation filter;
- `fact_type`: optional typed filter;
- `include_evidence`: whether to return drill-down references;
- `budget_tokens`: compact response budget.

Every result must expose its visibility and provenance:

```json
{
  "id": "...",
  "scope": "global",
  "project": "project-a",
  "source_chat_id": "chat-123",
  "content": "User prefers pytest",
  "confidence": 0.94,
  "evidence_refs": ["document-456"]
}
```

The default response is compact. Evidence is fetched only when requested or
when the agent needs to verify a fact.

## Alternatives considered

### Keep memory project-only

Simplest and safest, but repeated user preferences cannot be reused across
chats and projects.

### Copy all project memory into a global store

Rejected. This creates data leakage, unclear ownership, and difficult deletion
semantics.

### Adopt the full Tencent L0-L3 and host lifecycle

Rejected for the core. It introduces unnecessary coupling to host-agent
frameworks and makes derived persona state look like canonical data.

## Consequences

Positive:

- several chats can share one user's stable memory;
- project isolation remains the default boundary;
- summaries can be rebuilt and audited;
- existing CLI/MCP contracts can remain backward compatible;
- Tencent-style progressive disclosure becomes possible.

Costs and risks:

- a promotion policy and conflict resolution are required;
- derived-layer deletion must follow source deletion;
- extraction quality and stale facts need monitoring;
- future scheduler/checkpoint work adds operational complexity.

## Migration path

1. Define the Pydantic models and query filters without changing storage.
2. Add L1 extraction as an explicit/manual operation.
3. Add the `memory_facts` migration and rebuildable repositories.
4. Add CLI/MCP parity for search and recall.
5. Add deduplication, conflict handling, and evidence drill-down.
6. Add optional background extraction after quality metrics exist.
7. Consider L2 scenarios only after L1 precision, stale-rate, and recall-budget
   metrics are acceptable.

The first release must be disableable and must not alter existing notes,
tasks, history, files, or project search behavior.

## Acceptance criteria for implementation

- Default recall returns `global + current project + current chat`.
- Explicit project filters prevent unrelated project facts from being returned.
- Every active fact has at least one evidence reference.
- Global promotion is explicit or policy-validated.
- Deleting canonical evidence invalidates dependent derived facts.
- Existing CLI/MCP tests remain green and old search behavior is unchanged.
