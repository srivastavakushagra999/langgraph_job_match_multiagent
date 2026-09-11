import uuid

from langchain_core.messages import HumanMessage

from job_matcher.graph import app
from job_matcher.resume import parse_resume
from job_matcher.schemas import Preferences


def main() -> None:
    prefs = Preferences(
        role="AI Engineer",
        remote=True,
        salary_min=100000,
        currency="EUR",
        base_location="Netherlands",
        open_to_onsite_at_base=True,
    )
    resume_text = parse_resume("job_matcher/data/resume.pdf")
    with open("job_matcher/data/candidate_profile_kushagra.txt") as f:
        candidate_profile = f.read()

    # Fresh thread per test run — keeps smoke tests out of the real user thread.
    config = {"configurable": {"thread_id": f"test-{uuid.uuid4()}"}}

    # Turn 1: search
    app.invoke({
        "intent": "search",
        "preferences": prefs,
        "resume_text": resume_text,
        "candidate_profile": candidate_profile,
    }, config)

    # Turn 2: chat — only the new message; everything else comes from the checkpoint
    app.invoke({
        "intent": "chat",
        "chat_history": [HumanMessage("Why is the top job a good fit?")],
    }, config)

    state = app.get_state(config).values
    print("realistic_matches:", len(state["realistic_matches"]))
    for msg in state["chat_history"]:
        print(f"  {msg.type}: {msg.content}")


if __name__ == "__main__":
    main()
