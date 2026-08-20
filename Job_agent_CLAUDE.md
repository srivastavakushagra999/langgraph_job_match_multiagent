# CareerLens — Job-Matching Multi-Agent (Project Context)

## Goal
Personal AI agent that:
1. Takes my job preferences (role, remote/hybrid, salary target, location
   constraints) as structured input
2. Takes my resume (PDF upload) and parses it
3. Searches real job listings (RemoteOK public API, no auth:
   https://remoteok.com/api)
4. Scores each job's fit against my resume + preferences (0-100 + reasoning)
5. Returns a ranked list: job, fit score, why it fits/doesn't, and what
   specific skill/experience gap I should close to improve my chances for
   that job

Not just a search tool — it should reason about fit, not just keyword match.

## Agent should be proactive, not just literal
- Don't only search the exact keywords I give. If the agent judges that an
  adjacent role/title is also a strong or profitable match (e.g. I ask for
  "AI Engineer" but "LLM Platform Engineer" or "MLOps Engineer" or "Agentic
  AI Specialist" also fit well), search those too and include them, with a
  note on why it expanded the search.
- For any job that's a promising-but-not-quite-there fit (good role/salary/
  remote match but missing a specific skill), don't just flag the gap —
  suggest a concrete, actionable way to close it: a specific technology to
  learn, a project to build, or a certification/course. Not generic advice
  like "improve your skills."

## Example interaction I want
> "I want an AI Engineer job, fully remote, ~150k, based in Netherlands,
> open to working across Europe."

Agent should come back with something like:
- Job X — 82% fit — strong match on LangGraph/Python, salary in range,
  remote confirmed. Improve: add a public GitHub project showing
  production agent deployment (not just tutorials).
- Job Y — 55% fit — good backend match but they want RAG/vector DB
  experience I don't have listed on resume.

## Current state
Nothing built yet in this repo — `job_matcher/` doesn't exist here. Starting
from a clean slate. (Earlier notes below describing `data.py`/`tools.py`/
`graph_version.py`/`functional_version.py` as "already built" refer to a
prior prototype, not code present in this repo — treat the plan below as
the actual starting point.)

**Collaboration style**: I'm writing the implementation myself. Claude's
role here is to guide — explain concepts, propose structure, review code
I write, flag issues — not to write the agent code wholesale. I'm using
this project to learn LangGraph properly, not just to end up with a
working tool.

**Next step**: draft `schemas.py` — `Preferences`, `JobListing`,
`ScoredJob` pydantic models (see confirmed schema below).

## Decisions locked in
- **Resume input**: PDF upload, agent parses it (need a PDF-to-text step —
  e.g. `pypdf` or similar, keep it simple, no need for OCR)
- **Job source**: RemoteOK public JSON API (https://remoteok.com/api) —
  real data, no auth needed. Respect rate limits, don't hammer it in a loop.
- **Preferences**: structured Streamlit form input, no LLM parsing needed
  for these fields (see confirmed `Preferences` schema below) — plus one
  optional free text field for anything else the form doesn't capture
- Keep both Graph API and Functional API versions in sync as I extend this
  — I'm using this project to learn the framework, not just to get a
  working tool

## Architecture: multi-agent (this replaces the single-agent loop)

**Orchestrator**
- Entry point. Takes preferences (structured) + parsed resume text.
- Runs job search ONCE (RemoteOK, with proactive keyword expansion —
  adjacent titles, not just the literal role given — see "proactive"
  section above). Produces one job list.
- Fans out that same job list + resume + preferences to Score Agent and
  Dreamer Agent IN PARALLEL (this is the new LangGraph pattern to learn
  here — fan-out/fan-in, not a single sequential loop like the earlier
  prototype).
- Merges both agents' outputs into one final response with two clearly
  separated sections.

**Score Agent** (strict/realistic evaluator)
- Input: resume + preferences + job list.
- For each job: fit score (0-100), clear reasoning on what matches/doesn't
  (skills, salary, remote, location), and if it's a close-but-not-quite
  fit — a concrete quick-tweak or small PoC suggestion to close the gap.
- Tone: grounded, honest, no hype.

**Dreamer Agent** (aspirational/stretch evaluator)
- Same inputs as Score Agent, but looser fit threshold.
- Surfaces high-paying or high-upside roles where only a few skills are
  missing, even if not a strict current-profile match.
- Tone: motivating — explain why it's reachable, give a rough roadmap
  (what to learn, in what order, realistic timeframe) to become a
  competitive candidate for that role.
- Should NOT just repeat Score Agent's close matches — it's specifically
  for the stretch/reach jobs Score Agent would mark as too far.

**Implementation note**: follow the `agent_tool` pattern (sub-agents
called as tools from the orchestrator), not `strategy="handoff"` — same
reasoning as the Agentspan financial-advisor project: shared conversation
state across agents causes contamination. Each sub-agent should get a
clean, scoped input and return a structured result, not share message
history with the others.

## Confirmed schema and flow (design session 2026-08-20)

**`Preferences` model** — all structured form fields, no LLM parsing
needed (ambiguity like "4500 monthly — current or target?" and "remote
anywhere" vs. region-restricted remote listings is why these are explicit
fields, not free-text-extracted):
```python
class Preferences(BaseModel):
    role: str
    remote: bool
    salary_min: float
    currency: str                  # "EUR" | "USD" | "GBP" | ...
    base_location: str             # e.g. "Netherlands" — used to check
                                    # region-restricted remote listings,
                                    # NOT for relocation
    remote_scope: str               # "worldwide" | "EU" | specific region —
                                    # how wide a net for remote roles
    open_to_relocation: bool        # separate concept from remote_scope —
                                    # would they physically move
    additional_context: str | None  # optional free text: career-change
                                    # motivation, industries to avoid, etc.
                                    # Passed through as raw narrative to
                                    # Score/Dreamer prompts — never parsed
                                    # into structured fields.
```
`base_location` vs `remote_scope` split matters: RemoteOK listings are
often region-restricted ("Remote — US only") even when tagged remote, so
Score Agent needs the user's real base location to judge eligibility, not
just a `remote: true` flag. This is a hard fit-breaker rule for Score
Agent: a job whose remote eligibility excludes `base_location` should be
flagged plainly, not scored as a good match regardless of skill overlap.

**Confirmed flow** (no `extract_preferences` LLM step — removed after
deciding preferences are a structured form, not free text):
```
User fills structured form (required fields above) + optional free text
        │
        ▼
  parse_resume (PDF → text, plain function, OUTSIDE the graph)
        │
        ▼
  ORCHESTRATOR (LLM node, start of graph)
    - preferences (structured) + additional_context + resume_text
    - keyword expansion (adjacent titles), calls search_jobs → RemoteOK, once
        │
        ├──────────────┬──────────────┐   fan-out: distinct state keys,
        ▼              ▼              │   no reducers needed
  SCORE AGENT     DREAMER AGENT
        │              │
        └──────┬───────┘
               ▼
            MERGE → final result
```

**`OrchestratorState`** (the LangGraph state — checkpointed, traced):
```python
class OrchestratorState(TypedDict):
    preferences: Preferences        # input
    resume_text: str                # input
    job_listings: list[JobListing]  # written by orchestrator's search step
    expanded_keywords: list[str]    # why search grew beyond literal role —
                                     # kept visible for eval assertions
    realistic_matches: list[ScoredJob]  # written by Score Agent
    stretch_matches: list[ScoredJob]    # written by Dreamer Agent
```
Fan-out works with plain overwrite semantics (no `operator.add` reducer)
because Score and Dreamer write disjoint keys.

## What needs to change from current single-agent code
1. Replace `search_jobs` in `tools.py`: call RemoteOK API instead of
   `MOCK_JOBS`, filter by keyword + apply remote/salary filters where the
   API provides that data (RemoteOK jobs have `salary_min`/`salary_max`
   sometimes null — handle missing salary gracefully)
2. Add `parse_resume`: PDF → plain text (e.g. `pypdf`), done once at the
   start, passed into orchestrator state — not a repeated tool call
3. Split the single agent loop into orchestrator + score_agent +
   dreamer_agent as described above. Each sub-agent returns structured
   output (job, score, reasoning, suggestion/roadmap) — use a pydantic
   model or typed dict for this, not free text, so the UI can render it
   cleanly
4. Orchestrator merges both outputs into a single structured result:
   `{realistic_matches: [...], stretch_matches: [...]}`
5. Keep exploring this in both Graph API and Functional API where
   reasonable — Graph API is the more natural fit for fan-out/fan-in
   (parallel branches converging), so that version can lead; Functional
   API version can follow once the pattern is proven

## Observability, evals, and memory (agent best-practices layer)
Explicit goal for this project: not just a working agent, but one built the
way a production agent should be — traced, evaluated, and with a real
memory story. This is as much a learning target as the Graph vs Functional
API comparison.

**Observability — LangSmith**
- Native LangGraph integration, so this is the natural choice given the
  rest of the stack — trace every LLM/tool call across orchestrator +
  score_agent + dreamer_agent with no extra wiring beyond env vars
- `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`
  (e.g. `careerlens`)
- Use traces to inspect the fan-out/fan-in branches specifically — catch
  sub-agent output-parsing failures, compare latency/token cost of
  Score vs Dreamer, verify the orchestrator only calls RemoteOK once

**Evals**
- Build a small LangSmith eval dataset: representative
  (resume, preferences, job list) inputs with an expected output shape /
  quality bar
- Evaluators to write: reasoning is grounded in actual resume content (not
  hallucinated skills/experience), suggested skill-gap fixes are concrete
  and actionable (not "improve your skills"), Dreamer Agent's stretch
  matches are genuinely distinct from Score Agent's close matches (not
  just repeats with a looser label)
- Run the eval suite whenever orchestrator/score/dreamer prompts or logic
  change — not just ad hoc manual testing

**Memory**
- *Session-level (build now)*: LangGraph checkpointer (`MemorySaver`, or
  `SqliteSaver` if persistence across a single Streamlit session run is
  useful) so a failed sub-agent call can resume without re-running the
  whole graph, and so the fan-out/fan-in state is inspectable mid-run
- *Cross-session long-term (extension point, build later)*: a persistent
  Store keyed by user, to remember past resume versions, job IDs already
  surfaced (avoid re-showing the same job every run), and how fit scores
  trend as the resume/skills change over time. Keep this behind a clear
  seam (e.g. a `memory.py` wrapping a LangGraph `Store` or plain SQLite)
  so it drops in later without restructuring the agent graph.

## UI: Streamlit
- Simple Streamlit app (`app.py`) as the frontend — Python-only, fits
  existing stack, no separate frontend build needed
- Inputs: structured form for preferences (see confirmed `Preferences`
  schema above: role, remote, salary_min, currency, base_location,
  remote_scope, open_to_relocation) + optional free text field ("anything
  else about yourself or what you're looking for") + resume PDF uploader
- Output: two-section results view —
  - "Realistic Matches" — Score Agent results, as cards (job title,
    company, fit score, reasoning, tweak/PoC suggestion)
  - "Stretch Goals" — Dreamer Agent results, as cards (job title,
    company, why it's reachable, learning roadmap)
- Show a loading state while the agent runs (this can take a while with
  multiple LLM calls — search + score + dreamer in sequence/parallel)
- Keep it simple first pass — functional and clean over fancy; can
  iterate on styling once the underlying agent works

## My background (for the agent's own understanding of what I'm matching)
Senior Data Engineer (8+ yrs) transitioning into AI Engineering. Core:
Python, Spark, Hadoop, Azure/Databricks, SQL, PostgreSQL, Redis.
Agentic AI: LangGraph, LangChain, multi-agent orchestration, tool calling,
FastAPI. Built a production banking AI copilot orchestration service
(LangGraph on AKS) and a personal financial-research multi-agent project.
Based in Netherlands, working in Europe broadly is fine.

## Constraints
- Keep it runnable locally / on my Hetzner VM (CPX22, code-server) —
  Streamlit should bind to 0.0.0.0 and a configurable port so I can access
  it remotely
- `ANTHROPIC_API_KEY` via env var, never hardcoded
- `LANGCHAIN_API_KEY` (LangSmith) via env var, never hardcoded — tracing
  should be opt-in via `LANGCHAIN_TRACING_V2`, not silently always-on
- No database needed for session-level memory (checkpointer handles
  in-run state); cross-session long-term memory can start as a local
  SQLite file on the Hetzner VM — no external DB service required
- Add `streamlit`, `pypdf`, and `langsmith` to `requirements.txt`
