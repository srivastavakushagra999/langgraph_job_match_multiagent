from job_matcher.graph import app
from job_matcher.schemas import Preferences
from job_matcher.resume import parse_resume


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

    result = app.invoke({
        "preferences": prefs,
        "resume_text": resume_text,
        "candidate_profile": candidate_profile,
    })
    print(result)


if __name__ == "__main__":
    main()
