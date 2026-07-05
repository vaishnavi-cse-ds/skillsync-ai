# SkillSync AI — Agent Coding Guide

## Project Overview
SkillSync AI is a multi-agent career intelligence platform built with Google ADK 2.0.
It analyzes resumes, GitHub profiles, and coding platform stats to produce personalized
career roadmaps.

---

## Architecture

### Workflow Graph (`app/agent.py`)
```
START
  └─► input_parser (LlmAgent)
        └─► security_checkpoint (function node)
              ├─► [safe]  orchestrator (LlmAgent)
              │             └─► roadmap_generator (LlmAgent)
              │                   └─► final_output (function node)
              └─► [unsafe] security_event (function node)
                            └─► final_output (function node)
```

### Agents
| Agent | Role | Tools |
|---|---|---|
| `input_parser` | Parses raw text input into a structured UserInputSchema | — |
| `orchestrator` | Coordinates analysis, synthesizes OrchestratorReportSchema | AgentTool(resume_analyzer), AgentTool(profile_analyzer) |
| `resume_analyzer` | ATS score, resume feedback, skill gaps | — |
| `profile_analyzer` | GitHub & coding platform analysis | MCP: fetch_github_profile, fetch_coding_profile |
| `roadmap_generator` | Personalized learning path, project ideas, interview questions | MCP: search_learning_resources |

### MCP Server (`app/mcp_server.py`)
Three tools exposed via FastMCP (stdio transport):
- `fetch_github_profile(username)` — developer stats
- `fetch_coding_profile(platform, username)` — LeetCode/HackerRank/CodeChef stats
- `search_learning_resources(skills)` — curated tutorials, books, courses

---

## Key Implementation Rules

### EDGE RULE (Critical!)
Never create more than **one edge** between the same (source, target) pair.
Converging routes must use a single unconditional edge to the shared target.
```python
# WRONG — ValidationError at init:
(hitl_approval, final_output, "approved"),
(hitl_approval, final_output, "rejected"),

# CORRECT — single unconditional edge:
(hitl_approval, roadmap_generator, "approved"),
(hitl_approval, orchestrator, "rejected"),
# Then roadmap_generator → final_output (one unconditional)
```

### Model
- Always use `gemini-2.5-flash` (or `-lite`). Never `gemini-1.5-*` (retired, 404).
- Model is read from `GEMINI_MODEL` env var — change it in `.env`, NOT `config.py`.

### Windows Hot-Reload
`adk web` hot-reload is effectively disabled on Windows. After **any** code edit,
stop the server and relaunch:
```powershell
Get-Process -Id (Get-NetTCPConnection -LocalPort 18081,8090 -ErrorAction SilentlyContinue).OwningProcess | Stop-Process -Force
uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents
```

---

## Running Locally (Windows)
```powershell
# 1. Install dependencies
uv sync

# 2. Start the playground
uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents

# 3. Open http://localhost:18081 in your browser
```

## Test Payload
```json
{
  "resume_text": "John Doe. Experience: 2 years Python developer at TechCorp. Skills: Python, SQL, REST APIs. Education: B.Sc. Computer Science, State University 2022. Projects: Built inventory management system.",
  "github_username": "johndoe",
  "linkedin_url": "https://linkedin.com/in/johndoe",
  "coding_profiles": ["leetcode/johndoe"]
}
```

---

## Security Design
1. **Prompt Injection** — keyword detection at `security_checkpoint` node → `unsafe` route
2. **PII Scrubbing** — email + phone regex redaction before LLM processing
3. **Domain Validation** — input must contain resume keywords or is rejected
4. **Structured Audit Log** — JSON audit events to stderr on every decision

---

## File Map
```
skillsync-ai/
├── agents-cli-manifest.yaml   ← CLI project identity
├── pyproject.toml             ← Dependencies (pinned)
├── Makefile                   ← Dev commands
├── Dockerfile                 ← Container for cloud deploy
├── .env.example               ← Config template (copy to .env)
├── GEMINI.md                  ← This file
├── README.md                  ← Quick-start guide
├── SUBMISSION_WRITEUP.md      ← Competition write-up
├── DEMO_SCRIPT.txt            ← Spoken narration
├── assets/                    ← Diagrams and banner
│   ├── architecture_diagram.png
│   └── cover_page_banner.png
├── app/
│   ├── agent.py               ← All agents + Workflow graph
│   ├── config.py              ← AgentConfig (reads GEMINI_MODEL)
│   ├── mcp_server.py          ← FastMCP server (3 tools)
│   ├── fast_api_app.py        ← FastAPI + A2A + ReasoningEngine routes
│   └── app_utils/
│       ├── a2a.py             ← Agent-to-Agent protocol
│       ├── reasoning_engine_adapter.py
│       ├── services.py        ← Session/artifact services
│       ├── telemetry.py       ← OpenTelemetry setup
│       └── typing.py          ← Shared Pydantic types
├── tests/
│   ├── unit/
│   ├── integration/
│   └── eval/
└── deployment/
    └── terraform/
        └── single-project/    ← Vertex AI Agent Runtime Terraform
```
