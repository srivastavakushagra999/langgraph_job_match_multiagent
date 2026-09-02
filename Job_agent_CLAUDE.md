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

**`job_matcher/resume.py`** — `parse_resume(pdf_path)` using `pypdf`,
extracts text per page (`page.extract_text() or ""` to survive `None` on
a page with no extractable text layer — no OCR, per locked decision, so a
scanned-image resume would silently return empty text for that page
rather than erroring). **Locked decision (2026-08-29)**: the "uploaded
PDF vs. default `job_matcher/data/resume.pdf` fallback" branch lives in
`app.py`, not in `parse_resume`. `parse_resume` stays a plain
path-in/text-out function — no knowledge of uploads or fallbacks — since
`app.py` is the layer that already talks to Streamlit's `file_uploader`
(which returns `None` when nothing's uploaded) and needs to know which
source was used anyway, to show the "uploaded vs. default-on-file"
caption. Keeps `parse_resume` easy to unit-test and reusable (e.g.
`test_graph.py` needs plain resume text with no PDF involved at all).

## Session 2026-08-29 (Day 5) — orchestrator, score_agent, dreamer_agent all real

**All three LLM nodes are now implemented and confirmed working
end-to-end** via `test_graph.py` against a real resume PDF
(`job_matcher/data/resume.pdf`) and live Adzuna/Anthropic calls (no more
stubs except `merge`, which per the confirmed flow design is plain object
assembly, no LLM needed).

**`orchestrator`**: LLM call (`claude-haiku-4-5-20251001` — lightweight
judgment task, cheap model is fine) returns structured
`OrchestratorDecision {expanded_keywords, context_signals}` only; country
code mapping (`_map_country_code`, deterministic) and the actual
`search_jobs` call are plain code, not LLM-driven — same "LLM does
judgment, code does mechanical execution" principle used for the
country-code decision earlier. **Locked decision**: rejected exposing
`search_jobs` as a bindable LLM tool (`agent_tool`/tool-calling loop
pattern) — it would make execution shape (whether/how many times the tool
gets called) LLM-controlled instead of fixed, harder to eval/trace in
LangSmith (variable-length trace per run vs. one fixed-shape call), and
would reintroduce the country-code-hallucination risk since the LLM would
have to generate `country_code` itself as a tool argument.

**`score_agent`** and **`dreamer_agent`**: both use `claude-sonnet-5`
(stronger reasoning needed here — grounding claims in actual resume
content across up to ~39 jobs in one batched call is a heavier load than
orchestrator's keyword-expansion task). Both return a list of `JobScore
{job_id, fit_score, reasoning, gap_suggestion}` (schema currently named
`ScoreAgentOutput`, reused by both agents since the shape is identical —
worth a rename to something generic like `JobEvaluation` at some point,
not urgent) — deliberately NOT the full `ScoredJob` with a nested
`JobListing`, to avoid making the LLM reproduce fields like `url`/
`description` it doesn't need to touch. Code joins `job_id` back to the
real `JobListing` objects (from `state["job_listings"]`) to build actual
`ScoredJob` instances; an unmatched `job_id` is silently skipped rather
than crashing the node.

**Dreamer distinctness** — confirmed via a live run, not just designed:
Score Agent's top-rated job (fit_score 80) also appeared in Dreamer's
stretch picks, but Dreamer scored it 68, not 80 — because Dreamer's
system prompt explicitly requires `fit_score` to reflect *current* fit
(usually lower than a safe match), with the upside case made in
`reasoning`/`gap_suggestion` instead. Score and Dreamer run in parallel
(fan-out, no shared output at runtime per the doc's own architecture), so
this distinctness has to come from each prompt's own framing, not from
Dreamer excluding whatever Score already picked. Dreamer's prompt also
caps how far a stretch can go: the gap must be bridgeable by extending
current skills (e.g. Databricks → new cloud service in the same
ecosystem), not a from-scratch pivot into an unrelated field — even a
high-paying job gets excluded from stretch matches if it requires
starting from zero.

**New input: `candidate_profile`** — added `candidate_profile: str` to
`OrchestratorState`, sourced from a new gitignored file
(`job_matcher/data/candidate_profile_kushagra.txt`) — durable info about
the candidate (priorities, learning style) that doesn't belong in
per-run `additional_context` (which is per-search free text) or
`resume_text` (which is just facts/skills). This operationalizes the
`## My background` section already written elsewhere in this doc, which
previously wasn't actually wired into any prompt. Only `score_agent` and
`dreamer_agent` read it (`orchestrator`'s keyword-expansion task doesn't
need it) — Dreamer uses it most heavily, to judge what "high upside"
means for this specific candidate. **`.gitignore` changed** from the
single literal path `job_matcher/data/resume.pdf` to the whole
`job_matcher/data/` directory, after almost committing a real resume PDF
under a different filename (`Kushagra_Srivastava_sr_dataengineer_lst.pdf`)
that the old exact-path rule didn't catch — the directory itself is
meant for personal, gitignored inputs only.

**New file: `job_matcher/prompts.py`** — all system prompts and human-
prompt builder functions extracted out of `graph.py`, since 3 LLM nodes
each need a sizeable prompt and inlining them would make `graph.py`
mostly prompt text instead of graph wiring. `graph.py` now stays pure
control-flow + the deterministic joins.

**`tools.py` cleanup** (two bugs fixed this session, both previously
flagged as "known cleanup pending"): the `JobListing` import was missing
entirely (`from job_matcher.schemas import JobListing`); and
`ADZUNA_APP_ID`/`ADZUNA_APP_KEY` were read from `os.environ` at module
import time, which would crash on `import graph` (since `graph.py`
imports `tools.py`) before `.env` was ever loaded, and would also have
meant `test_graph.py`'s wiring smoke test needed real Adzuna credentials
just to import the graph. Fixed by moving `load_dotenv()` + the
`os.environ[...]` reads inside `_fetch_adzuna`, evaluated lazily only
when a real API call actually happens.

**Next step**: `merge` is the only remaining stub. Per the confirmed
design it should be plain code (no LLM) — `realistic_matches` and
`stretch_matches` are disjoint state keys already written by Score/
Dreamer, so `merge` just needs to assemble/pass through the final result
shape, no synthesis logic needed. After that: `app.py` (Streamlit UI),
the resume upload/fallback branch, and the country-dropdown restricted to
Adzuna's 19 supported codes are still fully unbuilt.

## Session 2026-08-31 (Day 6) — merge implemented, app.py built

**`merge`** (`job_matcher/graph.py`) — no longer a stub. Plain code, no LLM,
per the locked design: sorts `state["realistic_matches"]` and
`state["stretch_matches"]` each by `fit_score` descending
(`sorted(..., key=lambda scored_job: scored_job.fit_score, reverse=True)`)
and returns both. Confirmed via `test_graph.py` (real Adzuna + Anthropic
calls): 83 raw listings across 4 expanded keywords → 39 realistic matches
(scores `85→...→20`, correctly descending) + 5 stretch matches (scores
`48→...→38`, correctly descending). All 5 graph nodes
(orchestrator/score_agent/dreamer_agent/merge, `START`/fan-out/fan-in/`END`)
are now real, end-to-end confirmed working.

**`app.py`** (Streamlit UI, new file, repo root) — **built by Claude
directly this session**, a deliberate one-off exception to the
"user writes the implementation" collaboration style: I said I'm not
keen to build frontend myself, so Claude owns `app.py` specifically.
Backend (`job_matcher/`) stays mine to write; this doesn't change that.
- Form fields: `role`, `remote` checkbox, `salary_min` + `currency`
  (EUR/USD/GBP dropdown), `base_location` — dropdown built from
  `tools.COUNTRY_CODE_MAP` keys directly (the locked "restrict to
  Adzuna's 19 supported countries" decision — can't drift out of sync
  since it reads the same dict `_map_country_code` uses),
  `open_to_onsite_at_base` checkbox, optional free-text
  `additional_context`, PDF resume uploader.
- **Resume fallback implemented**: uploaded PDF wins if present
  (written to a temp file, parsed, temp file cleaned up in a `finally`);
  otherwise falls back to `job_matcher/data/resume.pdf`, erroring clearly
  if neither exists. A caption always shows which source was used
  (uploaded vs. default-on-file), per the locked "never silently score
  against a stale resume" decision from the 2026-08-21 session.
- `candidate_profile` read from `job_matcher/data/candidate_profile_kushagra.txt`
  directly in `app.py` (not user-facing input — it's the durable
  candidate-background file, same as `test_graph.py` already does).
- Results rendered as two `st.tabs`: "Realistic Matches" and "Stretch
  Goals," each as cards (title, company, fit score, location, salary,
  reasoning, gap/roadmap suggestion, listing link) via one shared
  `render_job_card` helper — reused across both tabs since `ScoredJob`'s
  shape is identical for Score and Dreamer output.
- `st.spinner` during the graph run (multiple LLM calls, can take
  10-30+s), `job_matcher_app.invoke(...)` wrapped in try/except so a
  failure shows `st.error` instead of a raw traceback.
- Added `.streamlit/config.toml` with `server.address = "0.0.0.0"` for
  the Hetzner VM constraint; port left at Streamlit's default,
  overridable via `--server.port`/`STREAMLIT_SERVER_PORT` without
  hardcoding, per the "configurable port" constraint.
- **Verified**: boots clean, serves HTTP 200
  (`.venv/bin/streamlit run app.py`).

**Bug found via real browser click-through, fixed same session**:
`score_agent` crashed on a real run — `1 validation error for
ScoreAgentOutput scores: Input should be a valid list` — the model's tool
output came back with the whole JSON blob nested as a string value inside
the `scores` field instead of a proper list. Root cause wasn't
`max_tokens` (confirmed `ChatAnthropic` defaults to 128k, plenty of
headroom) — it was sheer request size: `orchestrator` had returned **83**
raw job listings (4 expanded keywords × Adzuna results), and
`score_agent`'s prompt demands scoring *every* listing in one structured-
output call. Even the prior *successful* run had silently scored only 39
of 83, ignoring "do not skip any" — so this was already unreliable at
that volume, just failing loudly instead of quietly.

**Fix**: added `filter_top_jobs(job_listings, keywords, limit=30)` to
`tools.py` — plain code, no LLM, ranks jobs by how many
`expanded_keywords` words appear in the job's `position`/`tags` (case-
insensitive), sorts descending, takes the top 30. Wired into
`orchestrator` in `graph.py` right after `search_jobs`, before the
`return`. Re-ran `test_graph.py`: `job_listings` confirmed capped at
exactly 30, 35 scores returned total (realistic + stretch), no crash.
This is the pre-filtering escape hatch the 2026-08-20 design session had
already flagged as a future need ("if job_listings ever gets large,
pre-filter by simple keyword/tag overlap before scoring") — turned out to
be needed sooner than expected.

**`app.py` upgraded to stream node-by-node progress**: replaced
`job_matcher_app.invoke(...)` + `st.spinner` with
`job_matcher_app.stream(state, stream_mode="updates")` inside an
`st.status(..., expanded=True)` block. Each node's output arrives as its
own chunk (`{node_name: partial_state}`); the UI writes a `✅ <label>`
line as each one lands (orchestrator → score_agent/dreamer_agent →
merge) and manually accumulates `state.update(node_output)` per chunk
since there's no separate final-state return in streaming mode. Verified
booting cleanly after the change.

**Committed and pushed**: `b6ef6df` "Day 6: UI and merge in orchestrator"
(`Job_agent_CLAUDE.md`, `app.py`, `.streamlit/config.toml`,
`job_matcher/graph.py`, `job_matcher/tools.py` — the `.agents`/`.claude`
local tool-config directories deliberately left out of the commit).

**Next step**: per the original architecture doc, remaining unbuilt
pieces are observability (LangSmith env-var wiring) and the eval suite —
superseded in priority, though, by the chat + memory architecture design
below, which is now the locked next milestone.

## Design session 2026-08-31 (Day 6, cont. 2) — chat architecture: memory layers, thread/run split, comparison mechanics

Extended design conversation following the roadmap sketch above, working
through the mechanics of the unified chat graph in more depth before any
of it gets built.

**Resume-editing tool, narrowed further**: asked whether an existing MCP
server could shortcut the PDF-editing problem — checked, none configured
in this project (`.mcp.json` doesn't exist; only unrelated/unauthenticated
Canva/Figma/Google Drive connectors available globally). Concluded MCP
wouldn't help anyway: the difficulty isn't tooling, it's that PDF is a
fixed-layout format not designed for safe reflow-editing — true for any
tool, not a library gap. Confirms the earlier "generate fresh, don't edit
original" decision. `rendercv` (pip package, YAML → polished PDF via
typst) was live-tested in this session in an isolated scratchpad venv —
produced a clean one-page PDF from a hand-written sample YAML with zero
manual layout work, validating it as the render target for this feature.

**Locked: unify chat + search into one LangGraph graph, not app.py-level
branching.** Rejected going further into a fully open ReAct/tool-calling
loop for the *whole* system (LLM freely decides what to call, in what
order) — same reasoning as the earlier locked decision to keep
`search_jobs` out of an `agent_tool` pattern: variable execution shape is
harder to eval/trace in LangSmith, and deterministic steps (country-code
mapping, job filtering, sorting) shouldn't be delegated to LLM judgment,
just a new failure-mode surface for no benefit. **Middle ground kept**:
the heavy pipeline (`orchestrator → score/dreamer → merge`) stays a fixed,
deterministic graph exactly as built; only the new `chat` node gets
LLM-driven routing, and even there it's a *bounded* choice between a
small fixed set of next steps, not an open tool loop.

**Two distinct memory mechanisms — don't conflate them**:
1. **LangGraph checkpointer** (`SqliteSaver`, keyed by `thread_id`) — full
   `OrchestratorState` snapshotted automatically after every node. This is
   what actually powers "resume where I left off": `load_session` just
   needs the right `thread_id`, no manual state reconstruction. File-
   based, persists across restarts, but has **no built-in expiry** — grows
   unbounded until something explicitly prunes old threads. Not a v1
   concern (personal tool, small data) but flagged as a future cleanup
   TODO, same shape as the "unbounded `st.cache_data` growth" caution
   already known from Streamlit performance guidance.
2. **`memory.py` SQLite (`runs`/`scored_jobs`, schema already designed in
   the 2026-08-21 session)** — lightweight, long-term, cross-run
   *analytical* history: dedup ("seen this job before") and trend
   ("how did my fit score for X change"). Explicitly **not** what powers
   session resumption, and not queried at normal Q&A answer-time.

**What actually feeds the Q&A LLM call**: `resume_text` +
`realistic_matches`/`stretch_matches` (full `ScoredJob`, including the
nested `JobListing` — so location/salary/description questions are
answerable with zero extra fetch) + `candidate_profile` + recent chat
turns — plain context stuffing, same "no RAG needed" principle already
used for Score/Dreamer, pulled from checkpointed state, not from SQLite.

**LLM-context growth over a long chat — real concern, mitigated, not a
blocker**: every turn is stateless and resends full history, so cost/
latency grow with conversation length. Three levers, no new pattern
needed:
- **Prompt caching** (`cache_control: {"type": "ephemeral"}`) — biggest
  win, since `resume_text`/results are static within a session; only
  ~10% cost on cache hits instead of full price every turn.
- **History windowing** (send only last N turns) as a safety net if a
  chat genuinely runs long — not expected to matter much for a personal
  tool, but cheap insurance.
- **Cheaper model for the chat node** — `claude-haiku-4-5` (same tier
  already used for `orchestrator`) is plausible here since Q&A judgment
  is lighter than Score/Dreamer's grounding task.

**Locked: one `thread_id` per user, not per search-run.** Originally
proposed `thread_id == run_id` (new thread per search); reversed after
weighing it against wanting the chat to feel like one continuous
assistant relationship across many searches, not a reset each time.
Consequence worth remembering: **`job_listings`/`realistic_matches`/
`stretch_matches` are overwrite fields in `OrchestratorState`, not
accumulators** — a second search inside the same thread replaces them, so
chat can't recover a *previous* run's job data from live graph state once
a newer run has happened. This is exactly why `memory.py`'s per-run
SQLite rows still matter even with one continuous thread — checkpointer
state answers "what's true right now," SQLite answers "what was true in
an earlier run."

**Job-reference disambiguation across searches** (e.g. "that Amsterdam
job from before" after a second search has already overwritten state):
resolved as a language-grounding problem, not a mechanical timestamp
check — normal multi-turn reference resolution, provided each job's
`job_id` stays attached to its mention in the actual message *content*
sent to the LLM (not just pretty display text the UI shows), so the model
can recover the exact id from its own earlier turns rather than fuzzy-
matching on title/company. A lookup tool (`get_job_by_id` against
`scored_jobs`) backs this up for fetching authoritative/fresh detail once
an id is known. A plain marker message on each new search ("🔍 New search
run — keywords: [...]") adds a natural boundary in the transcript — kept
as an ordinary message, not a mid-conversation `system`-role turn, since
that feature is Opus-only and this project runs Sonnet 5/Haiku for these
nodes.

**Trend/comparison answering (e.g. "how did my resume update help?")**:
- Chat's `answer` path gets a `query_past_runs` tool: pulls the two most
  recent `runs` rows for the user from SQLite, then both runs'
  `scored_jobs`.
- **Three buckets, not a single diff** — because Adzuna is a live job
  board, the job pool itself shifts between searches independent of
  resume quality:
  1. **Overlapping jobs** (same `job_id` in both runs) → real before/after
     delta, the actual "did the resume help" signal.
  2. **New this run only** → no prior score to diff, but worth surfacing;
     could itself be a resume-improvement signal if the updated resume
     changed which `expanded_keywords` the orchestrator chose.
  3. **Dropped since last run** → surfaced but explicitly *not* framed as
     a regression — most likely explanation is the Adzuna listing expired
     or fell outside the new search's scope/cap, not resume quality.
- **Presentation**: an aggregate headline first (average fit_score
  before/after, counts moved up/down/flat), then a detail list of
  individual deltas sorted by magnitude (biggest movers first, both
  directions shown honestly, not just the positive ones).
- **Noise-vs-signal caveat**: `fit_score` is LLM judgment, not a
  deterministic computation, so small deltas (roughly ±5) shouldn't be
  narrated as real improvement/decline — only larger moves (~10+) get
  called out as meaningful; small ones get described as "roughly
  unchanged."

**Not started** — still a real architecture milestone (router node, chat
node with bounded intent routing, checkpointer wiring, `query_past_runs`
+ `get_job_by_id` tools, `OrchestratorState` changes to carry chat
history), deliberately deferred to a dedicated future build session.

## Design session 2026-08-31 (Day 6, cont.) — roadmap: chat + unify into one graph

**Discussed, not yet built** (next real milestone, bigger than a single
session):

- **Chat Q&A over existing results** — once a run finishes, let the user
  ask follow-up questions ("why is job X only 45%?") grounded in
  `resume_text` + `realistic_matches` + `stretch_matches`, without
  re-running the search. Small context (same "no RAG needed" reasoning
  as Score/Dreamer already use).
- **Resume-improvement tool** — rejected in-place PDF editing as the
  approach (this resume's PDF layout is multi-column/complex, and
  rewriting text inside an existing PDF while preserving layout is
  fragile with any tool, not a library/MCP limitation — PDF is a fixed-
  layout format, not built for reflow-safe editing). No MCP currently
  configured in this project either. **Locked direction instead**:
  generate a *fresh* resume from structured content, not edit the
  original. Prototyped with `rendercv` (pip package, YAML in -> polished
  PDF out via typst, no LaTeX needed) — live-tested this session with a
  sample YAML, produced a clean single-page PDF with zero manual layout
  work. Real flow would have the LLM emit resume content as structured
  output (reusing the `with_structured_output` pattern already used for
  Score/Dreamer) matching RenderCV's schema, then call `rendercv render`
  to produce the PDF — same "LLM does judgment, code does mechanical
  execution" principle used elsewhere in this doc.
- **Cross-session memory** (`memory.py`, SQLite, already schema-designed
  in the 2026-08-21 session below) — needed so returning to the app can
  default to loading the last session (skip re-searching) instead of
  always starting fresh.

**Locked architecture decision**: build the above as **one unified
LangGraph graph**, not as ad-hoc branching logic in `app.py` calling a
fixed pipeline. Specifically:
- A **conditional entry point** (`START` routed via a router
  function/node, not a plain `add_edge`) that checks whether a saved
  session exists for the user and routes to either a `load_session` node
  or straight into the existing `orchestrator` pipeline.
- **A LangGraph checkpointer** (`SqliteSaver`, per the existing
  session-memory plan) keyed by `thread_id`, so each chat turn is its own
  `invoke()` call (fits Streamlit's rerun-per-interaction model naturally)
  but state persists across turns without `app.py` manually threading it
  through.

**Why this over the simpler "app.py orchestrates, graph stays a fixed
pipeline" split** considered earlier in this session: keeps every
LLM/tool call across the whole user session traceable in one place in
LangSmith (the project's own explicit observability goal), and is the
first use of LangGraph's human-in-the-loop / multi-turn pattern in this
project — deliberately chosen partly *because* it's a pattern not yet
explored here, consistent with this project's "learn the framework
properly" goal, not just "ship a working tool."

**Not started** — this is a real architecture milestone (new router node,
new chat node, checkpointer wiring, `OrchestratorState` changes to carry
chat history), deliberately deferred to a dedicated future session rather
than bolted on at the end of Day 6.

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
