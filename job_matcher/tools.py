import re
import time
import requests
import os

ADZUNA_APP_ID = os.environ["ADZUNA_APP_ID"]
ADZUNA_APP_KEY = os.environ["ADZUNA_APP_KEY"]
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = [1, 2, 4]


def _fetch_adzuna(keyword: str, country_code: str) -> list[dict]:
    url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": keyword,
        "content-type": "application/json",
    }
    last_exc = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json().get("results", [])
        except requests.exceptions.HTTPError as exc:
            if 400 <= resp.status_code < 500:
                try:
                    detail = resp.json().get("display", resp.text)
                except ValueError:
                    detail = resp.text
                raise RuntimeError(
                    f"Adzuna rejected request (HTTP {resp.status_code}) for "
                    f"keyword={keyword!r}, country_code={country_code!r}: {detail}"
                ) from exc
            last_exc = exc
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(BACKOFF_SECONDS[attempt])
    raise RuntimeError(f"Adzuna fetch failed for keyword={keyword!r} after {MAX_ATTEMPTS} attempts") from last_exc

def search_jobs(keywords: list[str], country_code: str) -> list[JobListing]:
    all_jobs: dict[str, JobListing] = {}
    for keyword in keywords:
        raw_results = _fetch_adzuna(keyword, country_code)
        for item in raw_results:
            try:
                job = _to_job_listing(item)
            except (KeyError, AttributeError, TypeError) as exc:
                print(f"Skipping malformed job record: {exc}")
                continue
            all_jobs[job.id] = job
    return list(all_jobs.values())


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _to_job_listing(item: dict) -> JobListing:
    return JobListing(
        id=str(item["id"]),
        slug=str(item["id"]),
        position=item.get("title", "Unknown position"),
        company=item.get("company", {}).get("display_name", "Unknown company"),
        tags=[item.get("category", {}).get("label", "Unknown")],
        description=_strip_html(item.get("description", "")),
        location=item.get("location", {}).get("display_name", "Unknown location"),
        url=item.get("redirect_url", ""),
        date=item.get("created", ""),
        salary_min=item.get("salary_min") or None,
        salary_max=item.get("salary_max") or None,
    )

COUNTRY_CODE_MAP = {
    "Austria": "at", "Australia": "au", "Belgium": "be", "Brazil": "br",
    "Canada": "ca", "Switzerland": "ch", "Germany": "de", "Spain": "es",
    "France": "fr", "United Kingdom": "gb", "India": "in", "Italy": "it",
    "Mexico": "mx", "Netherlands": "nl", "New Zealand": "nz", "Poland": "pl",
    "Singapore": "sg", "United States": "us", "South Africa": "za",
}

def _map_country_code(base_location: str) -> str:
    if base_location not in COUNTRY_CODE_MAP:
        raise ValueError(f"No Adzuna country code mapping for base_location={base_location!r}")
    return COUNTRY_CODE_MAP[base_location]
