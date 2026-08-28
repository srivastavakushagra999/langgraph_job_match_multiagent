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

## Current state (updated 2026-08-23)
`job_matcher/schemas.py` is done — `JobListing`, `Preferences`, `ScoredJob`
pydantic models, all reviewed. Confirmed against real RemoteOK API output
(see "RemoteOK API — confirmed response shape" below). `fit_score` is
constrained `Field(ge=0, le=100)` since it's LLM judgment, not a computed
value — the range check is a backstop against hallucinated out-of-range
scores. (Earlier notes below describing `data.py`/`tools.py`/
`graph_version.py`/`functional_version.py` as "already built" refer to a
prior prototype, not code present in this repo.)

`job_matcher/state.py` — `OrchestratorState` (`TypedDict`), matches the
confirmed schema below exactly (preferences, resume_text, job_listings,
expanded_keywords, context_signals, realistic_matches, stretch_matches).

`job_matcher/graph.py` — graph skeleton wired and working:
`START → orchestrator → (score_agent ‖ dreamer_agent) → merge → END`,
fan-out/fan-in confirmed correct (disjoint-key writes merge with no
reducer needed). All four nodes are still stubs — each returns hardcoded
empty values for its output keys, no real LLM/tool logic yet.

`job_matcher/test_graph.py` — manual smoke test, `python -m
job_matcher.test_graph` (or `.venv/bin/python -m job_matcher.test_graph`
without activating). Builds a dummy `Preferences` + dummy `resume_text`,
calls `app.invoke(...)`, prints the final merged state. Confirmed working
2026-08-23 — full stub state came back correctly merged. This is the fast
feedback loop for wiring/logic changes going forward, no Streamlit or LLM
calls needed until `orchestrator` has real logic.

`.venv` exists in the repo root with `langgraph` etc. installed (per
`requirements.txt`, added 2026-08-23 — `langgraph`, `langchain-anthropic`,
`langsmith`, `streamlit`, `pypdf`, `requests`, `python-dotenv`, unpinned).

**Collaboration style**: I'm writing the implementation myself. Claude's
role here is to guide — explain concepts, propose structure, review code
I write, flag issues — not to write the agent code wholesale. I'm using
this project to learn LangGraph properly, not just to end up with a
working tool.

**Next step**: replace the `orchestrator` stub in `graph.py` with real
logic — read `preferences` + `resume_text`, decide `expanded_keywords`
(adjacent-title expansion) and `context_signals` (interpretation of
`additional_context`), call `search_jobs` against RemoteOK once. Score
and Dreamer stay stubs until Orchestrator produces real `job_listings` to
feed them. Not started yet.

## Design session 2026-08-28 — job source pivot: RemoteOK → Adzuna

**Why the switch**: RemoteOK has no server-side keyword search (must
fetch the entire feed and filter client-side) and its feed is noisy
(hotel/retail jobs mixed into "remote" listings — see confirmed shape
notes below, still accurate for the raw feed itself even though it's no
longer the chosen source). Explored alternatives that support real
server-side search:
- **Jobicy** (`jobicy.com/api/v2/remote-jobs?tag=...`) — free, no auth,
  supports comma-separated OR search across multiple tags/titles in one
  call. Rejected: confirmed via live test that its API returns **no
  salary field at all**, ever (not `null`, just absent from every job
  object) — a dealbreaker since `Preferences.salary_min` is a first-class
  field Score/Dreamer need to reason about.
- **Arbeitnow** (`arbeitnow.com/api/job-board-api`) — free, no auth, but
  `?search=` param is a no-op (confirmed live — returns the same generic
  page regardless of query) and no salary field either.
- **The Muse** (`themuse.com/api/public/jobs`) — `?category=` filtering
  works, but no salary field in the job object.
- **Adzuna** (`api.adzuna.com/v1/api/jobs/{country}/search/1`) — chosen.
  Requires free developer signup (`app_id`+`app_key`, no cost, just an
  extra step — registration form is generic/shared with job-board
  partners, personal/hobby use is fine). Confirmed via live testing:
  real keyword search AND real (if sometimes-missing) salary data in the
  same source — the only option found that has both.

**Adzuna keyword search — confirmed behavior (live-tested 2026-08-28)**:
- `what=` (plain): AND-of-individual-words, words don't need to be
  adjacent or in order. Single keyword works well (e.g. `what=ai
  engineer` correctly matches "AI Engineer", "AI Platform Engineer", "AI
  Solutions Engineer" etc.). **Breaks with 2+ keywords combined in one
  `what=` string** — demands all words from all keywords appear
  together, returns 0 results.
- `what_or=` with underscore-joined phrases (e.g. `what_or=ai_engineer
  mlops_engineer`) does proper OR-across-titles, but requires exact
  phrase adjacency — silently misses natural variants like "AI Platform
  Engineer" (a word wedged between "AI" and "Engineer" breaks the phrase
  match). Confirmed via live diff: this excludes exactly the kind of
  adjacent-title matches this project's proactive-search design wants to
  catch — rejected for that reason.
- **Locked approach**: call `search_jobs` once per keyword in
  `expanded_keywords` using plain `what=`, merge + dedupe results
  client-side by job `id`. More API calls than a single `what_or=` call,
  but correctly catches title variants (better recall), which matters
  more here than call count (keyword lists are short, 3-5 items).
- **No structured remote/eligibility field** — checked all 29 Adzuna
  categories, none relate to remote work; `location` is just a
  city/region/country object. Remote-ness (and region-restriction, e.g.
  "Remote (from Europe)" vs "100% Remote Worldwide") only shows up as
  free text sometimes in the title, sometimes literally inside
  `location.display_name`. **Locked decision: don't hard-filter remote
  eligibility in `search_jobs` — pass raw `location`/`title`/description`
  text through in `JobListing`, let Score Agent's LLM reasoning handle
  eligibility interpretation**, consistent with the "reason about fit,
  don't just keyword-match" philosophy elsewhere in this doc.
- **Country is a required path segment, not a query param** — Adzuna
  supports exactly 19 countries (`at, au, be, br, ca, ch, de, es, fr, gb,
  in, it, mx, nl, nz, pl, sg, us, za`), no worldwide/countryless option;
  an unsupported/missing code 404s with `UNSUPPORTED_COUNTRY`. **Locked
  decision: change the Streamlit `base_location` field from free text to
  a dropdown restricted to these 19 countries** (not yet implemented —
  `app.py` doesn't exist yet), so the backend's
  `COUNTRY_CODE_MAP`/`_map_country_code` lookup can never receive an
  unsupported value. Rejected letting the orchestrator LLM infer the
  country code — this is a deterministic lookup problem with one correct
  answer, not a judgment call worth spending an LLM call on, and an LLM
  could plausibly hallucinate a code outside the valid 19.
- **Salary shape**: `salary_min`/`salary_max` present as real numbers on
  some listings, `None` on others (same "sometimes missing" pattern as
  RemoteOK, not Jobicy's "always missing"). Also has
  `salary_is_predicted` (0 = from the actual posting, 1 = Adzuna's ML
  estimate) — not yet wired into `JobListing`/`ScoredJob`, worth adding
  so Score/Dreamer can distinguish posted vs. estimated salary. Saw one
  clearly-bad row (`salary_min: 600, salary_max: 1320` — not a
  believable annual figure, likely an unnormalized daily/monthly rate in
  Adzuna's raw feed) — no filter for this yet, worth a sanity-check
  threshold later.

**Built this session** (`job_matcher/tools.py`):
- `_fetch_adzuna(keyword, country_code)` — retry x3 with `[1,2,4]`s
  backoff, but only for transient failures (`ConnectionError`, `Timeout`,
  5xx). 4xx errors (e.g. bad country code, bad API key) raise immediately
  with Adzuna's own `display` error message surfaced in the exception —
  retrying a permanent client error wastes time since it'll never
  succeed.
- `search_jobs(keywords, country_code)` — loops keywords, calls
  `_fetch_adzuna` per keyword, converts + dedupes by job id.
- `_to_job_listing(item)` — raw Adzuna dict → `JobListing`. Uses `.get()`
  with fallbacks (not raw indexing) since Adzuna doesn't guarantee every
  field; `search_jobs` also wraps the conversion in
  `try/except (KeyError, AttributeError, TypeError): continue` so one
  malformed record doesn't crash the whole batch.
- `_strip_html(text)` — regex tag stripping for Adzuna's HTML-laden
  `description` field.
- `COUNTRY_CODE_MAP` + `_map_country_code(base_location)` — dict lookup,
  keyed on the exact country display strings the future dropdown will
  produce.
- **Known cleanup still pending** (deprioritized this session, not
  urgent): `JobListing` import missing from `tools.py` (will `NameError`
  as soon as it's actually run); `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` are
  read from `os.environ` at module import time, meaning anything
  importing `tools.py` before `.env` is loaded will crash — should be
  lazy-loaded inside `_fetch_adzuna` instead; malformed-record warning
  uses bare `print`, should be `logging` once observability work starts;
  minor PEP8 blank-line spacing inconsistencies.
- Added a `.gitignore` (didn't exist before this session — `.venv/`,
  `__pycache__/`, `.env`, `job_matcher/data/resume.pdf`, `*.sqlite`,
  `*.db`).

**`job_matcher/resume.py`** — started, not finished: `parse_resume(pdf_path)`
using `pypdf`, extracts text per page (`page.extract_text() or ""` to
survive `None` on a page with no extractable text layer — no OCR, per
locked decision, so a scanned-image resume would silently return empty
text for that page rather than erroring). Still open: does the
"uploaded PDF vs. default `job_matcher/data/resume.pdf` fallback" branch
live inside `parse_resume` itself, or in `app.py` with `parse_resume`
staying a plain path-in/text-out function? Not decided yet.

**Next step**: wire `search_jobs` into the `orchestrator` node in
`graph.py` — the LLM call that reads `preferences` + `resume_text` +
`additional_context`, decides `expanded_keywords` + `context_signals`,
then calls `search_jobs(expanded_keywords, country_code)` with what it
decided. Not started yet. `score_agent`/`dreamer_agent` remain stubs
until `orchestrator` produces real `job_listings`.

## RemoteOK API — confirmed response shape (checked 2026-08-21)
Pulled via `curl -s https://remoteok.com/api | python3 -m json.tool`.
Notes that matter for the `search_jobs` tool (not written yet):
- First array element is a legal-notice object (`{"legal": "...", "last_updated": ...}`),
  no `id`/`position` — must be skipped when parsing (`if "id" not in item: skip`).
- Real fields per job: `slug`, `id`, `epoch`, `date`, `company`,
  `company_logo`, `position`, `tags`, `description`, `location`,
  `apply_url`, `salary_min`, `salary_max`, `logo`, `url`.
- `salary_min`/`salary_max` are `0`, not `null`, when unspecified — must
  convert `0 → None` when building `JobListing` (`raw["salary_min"] or None`),
  otherwise "unknown salary" and "literally pays $0" are indistinguishable
  downstream. **Locked decision: never hard-filter out jobs with missing
  salary — always pass them through and let Score/Dreamer reason about the
  "unknown" explicitly**, since a missing salary field doesn't mean it's a
  bad match.
- `description` contains raw HTML tags and a spam-prevention boilerplate
  line ("Please mention the word **X**...") baked into every listing —
  pure noise, worth stripping before it reaches `JobListing`/LLM prompts
  (token cost + irrelevant to fit reasoning).
- The feed is noisier than expected — sample pull included a hotel Loss
  Prevention Officer and an H&M retail Sales Advisor, neither remote nor
  tech-related. Keyword filtering in `search_jobs` will be doing real
  work, not a formality.

## Decisions locked in
- **Resume input**: PDF upload, agent parses it (need a PDF-to-text step —
  e.g. `pypdf` or similar, keep it simple, no need for OCR)
- **Job source**: Adzuna API (see "Job source pivot" session below,
  2026-08-28 — supersedes the RemoteOK decision originally written here).
  Requires a free `app_id`/`app_key` signup, stored in `.env`
  (`ADZUNA_APP_ID`, `ADZUNA_APP_KEY`), never hardcoded.
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
    open_to_onsite_at_base: bool    # would they work non-remote IF the job
                                    # is physically at base_location — NOT
                                    # willingness to relocate elsewhere.
                                    # Non-remote job located anywhere other
                                    # than base_location is always rejected
                                    # regardless of this flag.
    additional_context: str | None  # optional free text: career-change
                                    # motivation, industries to avoid, etc.
                                    # Passed through as raw narrative to
                                    # Score/Dreamer prompts — never parsed
                                    # into structured fields.
```
`base_location` is used for a hard eligibility check: RemoteOK listings
are often region-restricted ("Remote — US only") even when tagged remote,
so Score Agent needs the user's real base location to judge eligibility,
not just a `remote: true` flag. This is a hard fit-breaker rule for Score
Agent: a job whose remote eligibility excludes `base_location` should be
flagged plainly, not scored as a good match regardless of skill overlap.

(2026-08-21: dropped a separate `remote_scope` field that was here
earlier — it would have added a "how wide a net for remote roles"
preference on top of eligibility, but the actual goal is simpler: show
jobs the user is eligible to work from `base_location`, nothing more.
`base_location` + `remote` alone answer that.)

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
  open_to_onsite_at_base) + optional free text field ("anything
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

## Design session 2026-08-21 — resume fallback, context handling, LLM mapping, memory schema

**Resume fallback**: if no PDF uploaded in the Streamlit form, fall back to
a default resume path in the repo (e.g. `job_matcher/data/resume.pdf`,
gitignored — never commit the actual PDF). UI should show a caption
indicating which source is in use (uploaded vs. default-on-file) so a run
never silently scores against a stale resume without you noticing.

**`additional_context` handling — added `context_signals` to state**:
free text (e.g. "13 years as Azure Data Engineer, want to move to AI
Engineering, currently ~4500/month, want more, also show me high-paying
jobs in my existing skill set") contains real signal beyond tone — it can
imply a second search intent (e.g. Azure/Data Engineer roles) distinct
from the literal `role` field. Rather than parsing it into new structured
fields (rejected — same ambiguity reasoning as the original schema
decision) or leaving it as inert flavor text, the Orchestrator LLM node
reads `additional_context` (not just `role`) when deciding
`expanded_keywords`, AND writes its own interpretation to a new state
field:
```python
class OrchestratorState(TypedDict):
    ...
    context_signals: str   # orchestrator's own read of additional_context —
                            # short interpretation (motivation, implied
                            # search intent, tone instructions for Dreamer)
                            # passed to both Score and Dreamer so they share
                            # one grounded understanding instead of each
                            # re-interpreting the raw paragraph independently
```
This keeps expansion as one coherent LLM-driven mechanism (reusing the
existing proactive-expansion logic) instead of a second separate one, and
gives LangSmith traces/evals something concrete to inspect ("did the
orchestrator correctly read the salary-motivation signal") instead of an
opaque raw paragraph.

**No RAG needed**: resume text (~1-2 pages) + preferences + job_listings
(tens of jobs after keyword filtering, not thousands) all fit comfortably
in a single LLM context window. Score/Dreamer prompts use plain context
stuffing (concatenate resume_text + preferences + context_signals +
job_listings directly), not embeddings/vector retrieval — RAG would only
become relevant if job history grew to thousands of entries via long-term
memory (not a v1 concern). If `job_listings` ever gets large, pre-filter
by simple keyword/tag overlap before scoring (cost/latency control, not
retrieval).

**LLM call mapping** (3 LLM nodes total per run):
- `parse_resume` — plain code (pypdf), NOT an LLM call
- Orchestrator — LLM call (reads preferences + resume_text +
  additional_context, decides expanded_keywords + context_signals, calls
  `search_jobs` tool via `agent_tool` pattern)
- Score Agent — LLM call (parallel w/ Dreamer)
- Dreamer Agent — LLM call (parallel w/ Score)
- Merge — plain code, NOT an LLM call (Score/Dreamer write disjoint state
  keys, so merge is just object assembly, no synthesis needed)
- Optional `summarize` node (new, after merge) — cheap/small model call,
  reads the already-merged structured result (+ memory, see below) to
  write a short narrative wrap-up. Kept as a separate node from `merge`
  specifically so `merge` stays deterministic.

**Memory layer — two distinct layers, don't conflate them**:
1. *Session-level (build now)*: LangGraph checkpointer (`MemorySaver`/
   `SqliteSaver`) snapshotting `OrchestratorState` per `thread_id` — purely
   for within-run resumability (e.g. Dreamer fails, don't re-run
   Orchestrator+Score). No new schema; just wraps existing state.
2. *Cross-session (`memory.py`, SQLite on the Hetzner VM)* — powers the
   `summarize` node's dedup/trend narrative. Schema:
   ```
   runs
   ├── run_id (PK)
   ├── user_id          -- hardcoded "kushagra" for now (single-user tool),
   │                        but present in schema so multi-user needs no
   │                        migration later, just an identity source in
   │                        the UI (e.g. a name field, no real auth needed)
   ├── timestamp
   ├── resume_hash       -- detect actual resume changes between runs
   ├── preferences_json

   scored_jobs
   ├── run_id (FK)
   ├── job_id            -- RemoteOK's own id, for cross-run dedup
   ├── title, company
   ├── category           -- "realistic" | "stretch"
   ├── fit_score
   ├── reasoning
   ├── gap_suggestion
   ```
   All queries scoped `WHERE user_id = ...` even though it's one hardcoded
   value today. Enables: dedup ("already seen this job"), trend ("your fit
   score for this job/category moved since last run, esp. after a resume
   change"). Treat fuzzy "did you close this specific gap" comparison
   (matching this run's reasoning against last run's stored
   `gap_suggestion` text) as a stretch feature, not v1 — build the tables
   and basic dedup/trend queries first, revisit once a few real runs of
   data exist to test against.
