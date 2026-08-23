from job_matcher.graph import app
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

    result = app.invoke({"preferences": prefs, "resume_text": "dummy resume text"})
    print(result)


if __name__ == "__main__":
    main()
