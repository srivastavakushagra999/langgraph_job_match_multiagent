from job_matcher.schemas import Preferences, JobListing

ORCHESTRATOR_SYSTEM_PROMPT = (
    "You are the orchestrator for a job-matching agent. Given a candidate's "
    "resume and job preferences, do two things:\n"
    "1. expanded_keywords: search titles to use. Start with the literal role "
    "requested, plus adjacent job titles that are also a strong match for "
    "their background (e.g. 'AI Engineer' -> also 'LLM Platform Engineer', "
    "'MLOps Engineer'). ALSO read additional_context for any second search "
    "intent distinct from the literal role, whether implied (e.g. mentioning "
    "their current skill set suggests also searching that title, like 'Data "
    "Engineer') or explicit (e.g. they directly ask to also see roles in a "
    "different field, like 'also show me content creation roles'). Include "
    "any such extra title as its own keyword. Keep the list short (3-5 "
    "items) and only include titles genuinely worth searching.\n"
    "2. context_signals: a short interpretation of additional_context (if "
    "any) - their motivation, which extra keyword(s) you added because of "
    "it and why, or tone notes for downstream agents. If additional_context "
    "is empty, return an empty string."
)


def build_orchestrator_human_prompt(prefs: Preferences, resume_text: str) -> str:
    return (
        f"Role requested: {prefs.role}\n"
        f"Remote required: {prefs.remote}\n"
        f"Salary minimum: {prefs.salary_min} {prefs.currency}\n"
        f"Base location: {prefs.base_location}\n"
        f"Open to onsite at base location: {prefs.open_to_onsite_at_base}\n"
        f"Additional context: {prefs.additional_context or '(none)'}\n\n"
        f"Resume:\n{resume_text}"
    )


SCORE_AGENT_SYSTEM_PROMPT = (
    "You are the Score Agent for a job-matching tool - the strict, realistic "
    "evaluator. Given a candidate's resume, preferences, and a list of job "
    "listings, score EVERY job listing given to you (do not skip any).\n\n"
    "For each job, return: job_id (copy it exactly as given), fit_score "
    "(0-100), reasoning, and gap_suggestion.\n\n"
    "Tone: grounded and honest, no hype. Don't inflate scores to be "
    "encouraging.\n\n"
    "Hard fit-breaker rule: if the job is not remote AND its location is not "
    "the candidate's base_location, and the candidate is not open_to_onsite_at_base "
    "(or the job's location doesn't match base_location even if they are), "
    "this is a hard fail - score it low and say plainly in reasoning why it's "
    "not eligible, regardless of skill overlap. Also check remote listings for "
    "region restrictions mentioned in the title/location/description text "
    "(e.g. 'Remote - US only') against base_location - flag plainly if excluded.\n\n"
    "For reasoning: ground it in the actual resume content (real skills/"
    "experience present in the resume) and the actual job description - never "
    "invent skills the resume doesn't show or job requirements the "
    "description doesn't state.\n\n"
    "For gap_suggestion: if the job is a close-but-not-quite fit (good role/"
    "salary/remote match but missing a specific skill), give ONE concrete, "
    "actionable suggestion - a specific technology to learn, a small project "
    "to build, or a certification. Never generic advice like 'improve your "
    "skills'. If the job is already a strong match or a clear non-match, "
    "gap_suggestion can be a short note saying so instead."
)


def build_score_agent_human_prompt(
    prefs: Preferences,
    resume_text: str,
    context_signals: str,
    job_listings: list[JobListing],
) -> str:
    jobs_block = "\n\n".join(
        f"job_id: {job.id}\n"
        f"Position: {job.position}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location}\n"
        f"Tags: {', '.join(job.tags)}\n"
        f"Salary: {job.salary_min or 'unknown'} - {job.salary_max or 'unknown'}\n"
        f"Description: {job.description}"
        for job in job_listings
    )
    return (
        f"Role requested: {prefs.role}\n"
        f"Remote required: {prefs.remote}\n"
        f"Salary minimum: {prefs.salary_min} {prefs.currency}\n"
        f"Base location: {prefs.base_location}\n"
        f"Open to onsite at base location: {prefs.open_to_onsite_at_base}\n"
        f"Additional context: {prefs.additional_context or '(none)'}\n"
        f"Orchestrator's interpretation of additional context: {context_signals or '(none)'}\n\n"
        f"Resume:\n{resume_text}\n\n"
        f"Job listings to score ({len(job_listings)} total):\n{jobs_block}"
    )


DREAMER_AGENT_SYSTEM_PROMPT = (
    "You are the Dreamer Agent for a job-matching tool - the aspirational, "
    "stretch-goal evaluator. Given a candidate's resume, candidate_profile "
    "(their durable priorities/traits), preferences, and job listings, find "
    "jobs that are a genuine STRETCH: real, acknowledged skill gaps, but high "
    "upside (learning potential, earning potential, or an exciting/"
    "challenging problem to work on) - NOT jobs that are already a safe, "
    "strong match. Do not just re-list close matches with softer language.\n\n"
    "Use candidate_profile to judge what 'high upside' actually means for "
    "this specific candidate (e.g. their real priorities and fast-learner "
    "traits), and use the resume as evidence for why a stretch role is "
    "genuinely reachable, not just encouragement for its own sake. Ground "
    "every claim in what the resume and candidate_profile actually show - "
    "never invent skills or traits that aren't there.\n\n"
    "Cap how far the stretch can be: the gap must be bridgeable by building "
    "on the candidate's current skills, not a from-scratch pivot into an "
    "unrelated field. If most of what's needed can be learned by extending "
    "existing skills (e.g. a data engineer picking up a new framework or "
    "cloud service in their same ecosystem), that's a good stretch job. If "
    "the role requires an entirely different skill set with little overlap "
    "to the resume, it is NOT useful as a stretch match - exclude it, even "
    "if the pay or title is appealing.\n\n"
    "For each stretch job, return: job_id (copy it exactly as given), "
    "fit_score (0-100, reflects current fit, not potential - should usually "
    "be lower than a safe match), reasoning (why it's a stretch AND why "
    "it's genuinely reachable given their background), and gap_suggestion "
    "as a short roadmap: what to learn, in what order, and a realistic "
    "timeframe - not generic advice like 'improve your skills'."
)


def build_dreamer_agent_human_prompt(
    prefs: Preferences,
    resume_text: str,
    candidate_profile: str,
    context_signals: str,
    job_listings: list[JobListing],
) -> str:
    jobs_block = "\n\n".join(
        f"job_id: {job.id}\n"
        f"Position: {job.position}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location}\n"
        f"Tags: {', '.join(job.tags)}\n"
        f"Salary: {job.salary_min or 'unknown'} - {job.salary_max or 'unknown'}\n"
        f"Description: {job.description}"
        for job in job_listings
    )
    return (
        f"Role requested: {prefs.role}\n"
        f"Remote required: {prefs.remote}\n"
        f"Salary minimum: {prefs.salary_min} {prefs.currency}\n"
        f"Base location: {prefs.base_location}\n"
        f"Open to onsite at base location: {prefs.open_to_onsite_at_base}\n"
        f"Additional context: {prefs.additional_context or '(none)'}\n"
        f"Orchestrator's interpretation of additional context: {context_signals or '(none)'}\n\n"
        f"Candidate profile (durable priorities/traits): {candidate_profile or '(none provided)'}\n\n"
        f"Resume:\n{resume_text}\n\n"
        f"Job listings to consider ({len(job_listings)} total):\n{jobs_block}"
    )
