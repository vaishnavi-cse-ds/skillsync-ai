# SkillSync AI

## Problem Statement

Every year, millions of developers struggle to navigate the gap between their current skill set and what the job market demands. Traditional career advice is generic, slow, and expensive. Resumes go unreviewed, GitHub profiles sit unnoticed, and the path forward is unclear.

**SkillSync AI** addresses this by providing an AI-powered, on-demand career intelligence platform that:
- Evaluates a candidate's resume for ATS compatibility and quality
- Analyzes their public technical profile (GitHub, LeetCode, HackerRank)
- Identifies specific skill gaps relative to market demand
- Generates a personalized, step-by-step learning roadmap
- Does all of this with human oversight at the critical decision point

Target users: students, early-career developers, and mid-career engineers considering a pivot.

---

## Solution Architecture

```
START
  └─► [input_parser] — parses raw plain text into structured UserInputSchema
        └─► [security_checkpoint] — PII scrub, injection detection, domain validation
              ├─[safe]──► [orchestrator] — delegates to sub-agents via AgentTool
              │             ├─► [resume_analyzer] — ATS score, feedback, skill gaps
              │             └─► [profile_analyzer] — GitHub & coding platform analysis
              │                      └─ uses MCP: fetch_github_profile, fetch_coding_profile
              │             └─► [roadmap_generator] — personalized learning plan
              │                      └─ uses MCP: search_learning_resources
              │                      └─► [final_output] — formatted markdown report
              └─[unsafe]─► [security_event] ─► [final_output] — security alert
```

All agents share state through `ctx.state`.

---

## Concepts Used

### ADK Multi-Agent Workflow

**File:** `app/agent.py`

Implemented using the ADK 2.0 Workflow graph API with function nodes and LlmAgent nodes connected by typed edges:

```python
root_agent = Workflow(
    name="skillsync_workflow",
    edges=[
        (START, input_parser),
        (input_parser, security_checkpoint),
        (security_checkpoint, {"safe": orchestrator, "unsafe": security_event}),
        (orchestrator, roadmap_generator),
        (roadmap_generator, final_output),
        (security_event, final_output),
    ],
    input_schema=RawUserInputSchema,
)
```

Inter-node data sharing uses `ctx.state` (e.g., `state["orchestrator_report"]`).

### LlmAgent Sub-Agents

Four `LlmAgent` instances with structured `output_schema`:

| Agent | Schema | Role |
|---|---|---|
| `resume_analyzer` | `ResumeAnalysisSchema` | ATS score + feedback + skill gaps |
| `profile_analyzer` | `ProfileAnalysisSchema` | GitHub + coding platform summary |
| `orchestrator` | `OrchestratorReportSchema` | Unified analysis synthesis |
| `roadmap_generator` | `RoadmapSchema` | Learning path + projects + interview questions |

### AgentTool (Orchestrator Delegation)

**File:** `app/agent.py` lines 143–146

The orchestrator delegates to sub-agents using `AgentTool`:
```python
orchestrator = LlmAgent(
    tools=[AgentTool(resume_analyzer), AgentTool(profile_analyzer)],
    ...
)
```
This enables true multi-agent coordination where the LLM decides which sub-agent to invoke and when.

### MCP Server

**File:** `app/mcp_server.py`

Three tools exposed via FastMCP using the stdio transport protocol:

| Tool | Purpose | Used By |
|---|---|---|
| `fetch_github_profile(username)` | Returns repo count, stars, languages, commit frequency | `profile_analyzer` |
| `fetch_coding_profile(platform, username)` | Returns problems solved, rank, badge details | `profile_analyzer` |
| `search_learning_resources(skills)` | Returns curated books, tutorials, and courses per skill | `roadmap_generator` |

The toolset is wired into agents via `McpToolset` with `StdioConnectionParams`, launching the MCP server as a subprocess.

### Security Checkpoint

**File:** `app/agent.py` — `security_checkpoint()` function node

Three-layer defense at the workflow entry:

1. **Prompt Injection Detection** — Keywords: `"ignore previous instructions"`, `"system prompt"`, `"override role"`, `"developer mode"`. Matched → `unsafe` route + CRITICAL audit log.
2. **Domain Validation** — Input must contain at least one of: `experience`, `skills`, `projects`, `education`, `work`, `university`, `employment`, `career`. Ensures only valid resumes are processed.
3. **PII Scrubbing** — Email addresses and phone numbers are replaced with `[EMAIL_REDACTED]` and `[PHONE_REDACTED]` using regex before any LLM processing.

Every decision generates a structured JSON audit log:
```json
{"event": "input_scrubbing_and_safety", "status": "allowed", "severity": "INFO", "details": {"emails_redacted": 1, "phone_numbers_redacted": 0}}
```

### Input Parsing & Fallback
 
At the entry point of the workflow, raw plain text submitted by the user is processed by `input_parser`. It extracts resume text, GitHub username, LinkedIn URL, and coding profiles automatically. If live LLM parsing fails due to API quota limits, a local regex-based fallback engine automatically extracts the metadata (e.g. usernames and profile links) to ensure uninterrupted session execution.

### Agents CLI

The project was scaffolded using `agents-cli` and is configured via `agents-cli-manifest.yaml`:
- `deployment_target: agent_runtime` — targets Vertex AI Agent Runtime
- `agent_directory: app` — the source directory containing `agent.py`
- `is_a2a: true` — enables Agent-to-Agent protocol endpoints

---

## Security Design

| Control | Implementation | Why It Matters |
|---|---|---|
| **Prompt Injection** | Keyword blocklist at `security_checkpoint` node | Prevents adversarial inputs from hijacking agent behavior |
| **PII Scrubbing** | Regex redaction of emails + phone numbers | Protects candidate privacy before any LLM processing |
| **Domain Validation** | Resume keyword check | Ensures only valid inputs reach expensive LLM calls |
| **Structured Audit Log** | JSON to stderr on every decision | Provides full auditability for compliance and debugging |
| **Input Schema Validation** | Pydantic `UserInputSchema` at workflow entry | Enforces type safety before any processing begins |

---

## MCP Server Design

The MCP server (`app/mcp_server.py`) uses **FastMCP** with stdio transport, launched as a subprocess by the parent ADK process. This enables:

- **Isolation**: The MCP server runs independently, preventing tool failures from crashing the main agent
- **Extensibility**: New tools can be added without modifying agent code
- **Portability**: The same MCP server can be reused by other agents in the future

Current tools return structured mock data simulating real API responses, making the system fully testable without external API dependencies.

## Fallback Engine Design
 
To ensure continuous operation under low API quota conditions (common with Gemini Free Tier API keys), we implemented fallback mechanisms across critical nodes:
1. **Input Parser Fallback:** If the LLM call fails, the node automatically falls back to regex-based extraction to grab the resume content, GitHub profile, and LinkedIn URL locally.
2. **Roadmap Generator Fallback:** If the LLM call fails, the node falls back to generating a comprehensive roadmap locally based on the identified skill gaps in the orchestrator report.
 
This makes SkillSync AI an extremely resilient agentic system that never crashes due to API exhaustion.
 
---
 
## Demo Walkthrough
 
### Test Case 1 — Full Happy Path
Send a raw plain text message with resume details and coding links (e.g. *"Jane Smith. 3 years Python developer. My github is janesmith..."*). The input parser extracts the parameters, the safety checkpoint validates them, the orchestrator performs the analysis, and the roadmap is generated and displayed instantly.
 
### Test Case 2 — Security Block
Send an adversarial payload (e.g. *"ignore previous instructions..."*). The input parser extracts the text, and the security checkpoint blocks the request immediately with a CRITICAL audit log to stderr. No downstream agents or MCP tools are called.
 
---
 
## Impact / Value Statement
 
**Who benefits:**
- **Students** — Get a clear, personalized path from where they are to where they want to be
- **Mid-career developers** — Quickly identify what skills to upskill for their next role
- **Career coaches** — A scalable tool to serve more clients with consistent, data-driven insights
- **HR teams** — An unbiased first-pass screening aid with full audit trails
 
**Why it matters:**
Personalized career guidance was previously accessible only to those who could afford coaches or mentors. SkillSync AI democratizes this intelligence, making it available on-demand to anyone with a resume and a GitHub profile.
 
The security-first design ensures the system can be safely deployed in professional environments where data privacy is critical.
 
