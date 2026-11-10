"""Scrape the public contribution calendar + repo count into data/contributions.json."""
import json, os, re, urllib.request
from pathlib import Path

USER = os.environ.get("GH_USER", "RajvirGautam")
ROOT = Path(__file__).resolve().parent.parent


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "readme-cards", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()


html = get(f"https://github.com/users/{USER}/contributions")
levels = dict(re.findall(r'data-date="(\d{4}-\d\d-\d\d)" id="(contribution-day-component-\d+-\d+)"', html))
by_id = {v: k for k, v in levels.items()}
counts = {}
for cid, text in re.findall(r'for="(contribution-day-component-\d+-\d+)"[^>]*>([^<]*)', html):
    m = re.match(r"\s*(\d+|No) contribution", text)
    if cid in by_id and m:
        counts[by_id[cid]] = 0 if m.group(1) == "No" else int(m.group(1))
days = [{"date": d, "count": counts.get(d, 0)} for d in sorted(levels)]

headers = {}
if os.environ.get("GITHUB_TOKEN"):
    headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
user = json.loads(get(f"https://api.github.com/users/{USER}", headers))

out = {"user": USER, "public_repos": user.get("public_repos", 0), "days": days}
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data" / "contributions.json").write_text(json.dumps(out, indent=1))
print(f"{len(days)} days, {sum(d['count'] for d in days)} contributions, {out['public_repos']} repos")
