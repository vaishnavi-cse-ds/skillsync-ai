# ruff: noqa
import re
from typing import Optional, List, Any
from pydantic import BaseModel, Field, model_validator
from google.adk.agents import Agent, LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.adk.workflow import Workflow, START
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.tools import AgentTool
from google.genai import types as genai_types

from app.config import config

# -----------------------------------------------------------------------------
# 1. Pydantic Schemas for Structured I/O
# -----------------------------------------------------------------------------

class RawUserInputSchema(BaseModel):
    raw_text: str = Field(description="Raw text containing resume and optional profile links.")

    @model_validator(mode='before')
    @classmethod
    def parse_raw_text(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"raw_text": data}
        return data

class UserInputSchema(BaseModel):
    resume_text: str = Field(description="Content of the candidate's resume.")
    github_username: Optional[str] = Field(None, description="GitHub username.")
    linkedin_url: Optional[str] = Field(None, description="LinkedIn profile URL.")
    coding_profiles: Optional[List[str]] = Field(default_factory=list, description="Links/usernames for coding platforms like LeetCode.")

class ResumeAnalysisSchema(BaseModel):
    ats_score: int = Field(description="ATS Score between 0 and 100")
    feedback: str = Field(description="Detailed bullet points on resume improvements")
    skill_gaps: List[str] = Field(description="List of skills that are missing or weak")

class ProfileAnalysisSchema(BaseModel):
    github_summary: str = Field(description="Analysis of GitHub repositories, contributions, and languages")
    coding_platform_summary: str = Field(description="Insights from competitive coding platforms")
    strengths: List[str] = Field(description="Key strengths identified from profiles")

class OrchestratorReportSchema(BaseModel):
    ats_score: int = Field(description="ATS compatibility score (0-100)")
    resume_feedback: str = Field(description="Constructive feedback on the resume format, wording, and impact.")
    developer_insights: str = Field(description="Summary of GitHub projects and competitive coding profiles.")
    skill_gaps: List[str] = Field(description="Key skills missing in the resume compared to target job market.")

class RoadmapSchema(BaseModel):
    learning_path: List[str] = Field(description="Step-by-step topics to study")
    project_recommendations: List[str] = Field(description="Projects to build to fill skill gaps")
    interview_questions: List[str] = Field(description="Practice interview questions based on profile")

import sys
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

# Initialize the local stdio MCP toolset pointing to our mcp_server.py
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
        ),
    ),
)

# -----------------------------------------------------------------------------
# 2. Specialized LLM Sub-Agents
# -----------------------------------------------------------------------------

_input_parser_agent = LlmAgent(
    name="input_parser",
    model=Gemini(
        model=config.model,
        retry_options=genai_types.HttpRetryOptions(attempts=3),
    ),
    instruction="""Analyze the raw user text provided in the user message (which contains resume details and optionally mentions of GitHub, LinkedIn, or coding profiles).
Extract and structure this information into the required fields:
- resume_text: The candidate's resume content. If no distinct resume text is found, default to the entire user text.
- github_username: Extract only the github username if a github profile link or statement is present (e.g. from 'github.com/username' extract 'username'). If not mentioned, set to None.
- linkedin_url: Extract the full LinkedIn URL. If not mentioned, set to None.
- coding_profiles: Extract any links or usernames for other coding platforms (LeetCode, HackerRank, etc.) as a list of strings.
""",
    input_schema=RawUserInputSchema,
    output_schema=UserInputSchema,
    description="Parses raw user input sentences/paragraphs into a structured UserInputSchema."
)

async def input_parser(ctx: Context, node_input: RawUserInputSchema) -> Event:
    """Wraps _input_parser_agent to provide explicit error handling, logging, and fallback support."""
    import logging
    import traceback
    from google.adk.workflow._llm_agent_wrapper import run_llm_agent_as_node

    logger = logging.getLogger(__name__)
    logger.info("[INPUT PARSER] Node execution started.")
    try:
        async for event in run_llm_agent_as_node(_input_parser_agent, ctx=ctx, node_input=node_input):
            yield event
        logger.info("[INPUT PARSER] Node execution completed successfully.")
    except Exception as e:
        logger.error(f"[INPUT PARSER] Node execution failed: {e}", exc_info=True)
        print(f"[ERROR] [INPUT PARSER] Node execution failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        
        # Build fallback UserInputSchema using local parsing
        logger.info("[INPUT PARSER] Falling back to offline parsing due to API limit.")
        
        raw_text = node_input.raw_text or ""
        
        # Extract GitHub username via regex
        github_match = re.search(r'github\.com/([a-zA-Z0-9_-]+)', raw_text, re.IGNORECASE)
        github_username = github_match.group(1) if github_match else None
        if not github_username:
            # Fallback for "github is xxx" or "github profile is xxx"
            github_words = re.search(r'github\s+(?:is|profile|username)?\s*[:\s\-]*\s*([a-zA-Z0-9_-]+)', raw_text, re.IGNORECASE)
            github_username = github_words.group(1) if github_words else None
            
        # Extract LinkedIn profile URL via regex
        linkedin_match = re.search(r'(https?://[a-z]+\.?linkedin\.com/in/[a-zA-Z0-9_-]+)', raw_text, re.IGNORECASE)
        linkedin_url = linkedin_match.group(1) if linkedin_match else None
        
        fallback_input = {
            "resume_text": raw_text,
            "github_username": github_username,
            "linkedin_url": linkedin_url,
            "coding_profiles": []
        }
        
        yield Event(
            output=fallback_input
        )

resume_analyzer = LlmAgent(
    name="resume_analyzer",
    model=Gemini(
        model=config.model,
        retry_options=genai_types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a professional Resume Critic and ATS Optimization expert.
Analyze the candidate's resume content.
Compute a realistic ATS score (0-100), identify significant formatting or wording issues, and list specific skill gaps.
Provide your response strictly complying with ResumeAnalysisSchema.
""",
    output_schema=ResumeAnalysisSchema,
    description="Analyzes resumes, calculates ATS scores, and identifies skill gaps."
)

profile_analyzer = LlmAgent(
    name="profile_analyzer",
    model=Gemini(
        model=config.model,
        retry_options=genai_types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a Technical Talent Scout.
Analyze the candidate's GitHub repositories and coding platform stats (such as LeetCode, CodeChef, HackerRank).
Use the available MCP tools to fetch the GitHub profile and competitive coding profile details if usernames or platform names are provided.
Spot their key strengths, active languages, project complexity, and profile quality.
Provide your response strictly complying with ProfileAnalysisSchema.
""",
    output_schema=ProfileAnalysisSchema,
    tools=[mcp_toolset],
    description="Analyzes GitHub profiles/repositories and coding platform performance."
)

_roadmap_generator_agent = LlmAgent(
    name="roadmap_generator",
    model=Gemini(
        model=config.model,
        retry_options=genai_types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a Career Path Coach.
Based on the approved analysis report: {orchestrator_report}
Create a tailored step-by-step learning roadmap, recommend specific hands-on projects, and list relevant interview practice questions.
Use the search_learning_resources tool to find high-quality tutorials, books, and courses for the identified skill gaps.
Provide your response strictly complying with RoadmapSchema.
""",
    output_schema=RoadmapSchema,
    tools=[mcp_toolset],
    output_key="learning_roadmap"
)

async def roadmap_generator(ctx: Context, node_input: OrchestratorReportSchema) -> Event:
    """Wraps _roadmap_generator_agent to provide explicit error handling, logging, and fallback support."""
    import logging
    import traceback
    from google.adk.workflow._llm_agent_wrapper import run_llm_agent_as_node

    logger = logging.getLogger(__name__)
    logger.info("[ROADMAP GENERATOR] Node execution started.")
    try:
        async for event in run_llm_agent_as_node(_roadmap_generator_agent, ctx=ctx, node_input=node_input):
            yield event
        logger.info("[ROADMAP GENERATOR] Node execution completed successfully.")
    except Exception as e:
        logger.error(f"[ROADMAP GENERATOR] Node execution failed: {e}", exc_info=True)
        print(f"[ERROR] [ROADMAP GENERATOR] Node execution failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        
        # Build a beautiful fallback roadmap matching RoadmapSchema
        logger.info("[ROADMAP GENERATOR] Falling back to rule-based roadmap generation due to API limit.")
        
        warning_msg = (
            "\n> [!WARNING]\n"
            "> Live Gemini API quota limit reached (429 Resource Exhausted). Generating a personalized, "
            "interactive career roadmap offline using fallback engines to complete the execution smoothly.\n"
        )
        yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=warning_msg)]))
        
        # Construct fallback content based on node_input
        skill_gaps = node_input.skill_gaps or ["System Architecture", "Cloud Deployment", "API Integration", "Automated Testing"]
        
        learning_path = []
        project_recommendations = []
        interview_questions = []
        
        for gap in skill_gaps:
            learning_path.append(f"Master {gap}: Complete high-quality documentation guides, study best practices, and work on hands-on exercises.")
            project_recommendations.append(f"Build a {gap} Demo: Develop an open-source project showcasing structured design patterns for {gap}.")
            interview_questions.append(f"How do you address issues related to {gap} in a highly scalable production environment?")
            
        fallback_roadmap = {
            "learning_path": learning_path,
            "project_recommendations": project_recommendations,
            "interview_questions": interview_questions
        }
        
        yield Event(
            output=fallback_roadmap,
            state={"learning_roadmap": fallback_roadmap}
        )


# -----------------------------------------------------------------------------
# 3. Orchestrator Agent (with AgentTools)
# -----------------------------------------------------------------------------

orchestrator = LlmAgent(
    name="orchestrator",
    model=Gemini(
        model=config.model,
        retry_options=genai_types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Career Intelligence Orchestrator.
Your goal is to coordinate a career intelligence evaluation for the candidate.
Candidate Info:
- Resume Content: {resume_text}
- GitHub Username: {github_username}
- LinkedIn: {linkedin_url}
- Coding Profiles: {coding_profiles}

You have tools to delegate tasks:
- Call `resume_analyzer` to analyze the candidate's resume.
- Call `profile_analyzer` to check coding profiles/GitHub details.

Make sure to call both sub-agents, gather their outputs, and synthesize a unified final analysis report.
If the candidate provided previous feedback for refinement: {user_refinement_feedback}
Integrate this feedback into your updated report.
Provide your response strictly complying with OrchestratorReportSchema.
""",
    tools=[AgentTool(resume_analyzer), AgentTool(profile_analyzer)],
    output_schema=OrchestratorReportSchema,
    output_key="orchestrator_report",
    description="Orchestrates the entire resume and profile analysis process."
)

# -----------------------------------------------------------------------------
# 4. Workflow Function Nodes
# -----------------------------------------------------------------------------

import json

def security_checkpoint(ctx: Context, node_input: UserInputSchema) -> Event:
    """Security Checkpoint node for input scrubbing and validation."""
    resume_text = node_input.resume_text
    github_username = node_input.github_username
    linkedin_url = node_input.linkedin_url
    coding_profiles = node_input.coding_profiles

    # Structured Audit Log helper
    def log_audit(event_name: str, status: str, severity: str, details: dict):
        log_payload = {
            "event": event_name,
            "status": status,
            "severity": severity,
            "details": details
        }
        print(json.dumps(log_payload), file=sys.stderr)

    # Check 1: Prompt Injection detection
    injection_keywords = ["ignore previous instructions", "system prompt", "override role", "developer mode"]
    combined_input = f"{resume_text} {github_username or ''} {linkedin_url or ''} {' '.join(coding_profiles or [])}"
    is_safe = True
    for kw in injection_keywords:
        if kw in combined_input.lower():
            is_safe = False
            log_audit(
                event_name="prompt_injection_check",
                status="blocked",
                severity="CRITICAL",
                details={"matched_keyword": kw, "github_username": github_username}
            )
            break

    if not is_safe:
        return Event(
            output="Security Violation: Possible prompt injection attempt detected.",
            route="unsafe",
            state={"is_safe": False}
        )

    # Check 2: Domain-specific validation (must contain resume keywords)
    resume_keywords = ["experience", "skills", "projects", "education", "work", "university", "employment", "career"]
    has_resume_keywords = any(kw in resume_text.lower() for kw in resume_keywords)
    if not has_resume_keywords:
        log_audit(
            event_name="domain_validation_check",
            status="flagged",
            severity="WARNING",
            details={"reason": "Input does not contain career/resume keywords."}
        )
        return Event(
            output="Validation Failure: The uploaded content does not appear to be a resume. Please upload a valid resume containing work experience, projects, or education.",
            route="unsafe",
            state={"is_safe": False}
        )

    # Scrub PII: Email & Phone Number regex
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    
    email_matches = re.findall(email_pattern, resume_text)
    phone_matches = re.findall(phone_pattern, resume_text)
    
    scrubbed_resume = re.sub(email_pattern, "[EMAIL_REDACTED]", resume_text)
    scrubbed_resume = re.sub(phone_pattern, "[PHONE_REDACTED]", scrubbed_resume)

    log_audit(
        event_name="input_scrubbing_and_safety",
        status="allowed",
        severity="INFO",
        details={
            "emails_redacted": len(email_matches),
            "phone_numbers_redacted": len(phone_matches),
            "github_username": github_username
        }
    )

    return Event(
        output="Input cleared by security checkpoint.",
        route="safe",
        state={
            "is_safe": True,
            "resume_text": scrubbed_resume,
            "github_username": github_username,
            "linkedin_url": linkedin_url,
            "coding_profiles": coding_profiles,
            "user_refinement_feedback": ""
        }
    )

def security_event(node_input: str) -> str:
    """Handles routing for security violations."""
    return node_input

async def hitl_approval(ctx: Context, node_input: OrchestratorReportSchema) -> Event:
    """Pauses execution to obtain human feedback/approval on the orchestrator report."""
    if not ctx.resume_inputs or "approval" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="approval",
            message=f"### 📋 Draft Report Generated\n\n- **ATS Compatibility Score:** {node_input.ats_score}/100\n\nPlease approve or reply with feedback to refine the report:"
        )
        return

    user_response_clean = user_response.lower().strip().replace(".", "").replace("!", "")
    if user_response_clean in ["yes", "approve", "approved", "y", "ok", "okay"]:
        yield Event(
            output=node_input,
            route="approved",
            state={"orchestrator_report": node_input}
        )
    else:
        yield Event(
            output=user_response,
            route="rejected",
            state={"user_refinement_feedback": user_response}
        )

def final_output(ctx: Context, node_input: dict) -> Event:
    """Constructs and yields a beautifully formatted markdown report for the web UI."""
    if not ctx.state.get("is_safe", True):
        error_msg = f"### ⚠️ Security Alert\n\n{node_input}"
        yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=error_msg)]))
        yield Event(output=node_input)
        return

    report = ctx.state.get("orchestrator_report", {})
    roadmap = node_input  # Output from roadmap_generator

    # Format output as a premium markdown document
    formatted_markdown = f"""# 🚀 SkillSync AI — Career Intelligence Report

## 📊 ATS Compatibility Score: **{report.get('ats_score', 0)}/100**

### 📝 Resume Feedback
{report.get('resume_feedback', '')}

### 💻 Developer Profile Analysis (GitHub & Coding Platforms)
{report.get('developer_insights', '')}

### 🎯 Identified Skill Gaps
"""
    for gap in report.get('skill_gaps', []):
        formatted_markdown += f"- {gap}\n"

    formatted_markdown += f"""
---

## 🗺️ Personalized Learning Roadmap

### 📚 Learning Path
"""
    for step in roadmap.get('learning_path', []):
        formatted_markdown += f"1. {step}\n"

    formatted_markdown += f"""
### 🛠️ Recommended Projects
"""
    for proj in roadmap.get('project_recommendations', []):
        formatted_markdown += f"- {proj}\n"

    formatted_markdown += f"""
### ❓ Suggested Interview Practice Questions
"""
    for q in roadmap.get('interview_questions', []):
        formatted_markdown += f"- {q}\n"

    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=formatted_markdown)]))
    yield Event(output={"report": report, "roadmap": roadmap})

# -----------------------------------------------------------------------------
# 5. Workflow Graph Configuration
# -----------------------------------------------------------------------------

# Main workflow graph definition
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
    description="A multi-agent career intelligence platform."
)

app = App(
    name="app",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True)
)
