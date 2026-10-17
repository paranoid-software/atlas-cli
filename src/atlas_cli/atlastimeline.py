"""The activity of an Atlas over a window of days: SPEC stamps, findings and SPEC-branch commits."""
import datetime
from pathlib import Path

from atlas_cli.atlascorpus import read_corpus
from atlas_cli.atlasfiles import ATLAS_TOML, read_atlas_toml
from atlas_cli.sourcedeclaration import declared_repos
from atlas_cli.sourcegit import spec_commits
from atlas_cli.sourcestate import judge_source


def read_timeline(folder: Path, days: int | None, today: datetime.date | None = None) -> dict:
    """Events newest first within the last `days` (None = everything), and a count per day."""
    today = today or datetime.date.today()
    corpus = read_corpus(folder)
    titles = {spec["number"]: (spec["name"], spec["title"]) for spec in corpus["specs"]}
    events = [event for spec in corpus["specs"] for event in _spec_events(spec)]
    since = (today - datetime.timedelta(days=days - 1)).isoformat() if days is not None else None
    read: set[Path] = set()
    for name in _repos(folder):
        path = (folder / name).resolve()
        if path in read:
            continue  # the same repo reached through two sources counts once
        read.add(path)
        for commit in spec_commits(folder / name, name, since):
            spec_name, title = titles.get(commit["number"], (f"SPEC_{commit['number']}", ""))
            events.append({"date": commit["date"], "kind": "commit", "spec": spec_name, "title": title,
                           "repo": commit["repo"], "detail": commit["detail"]})
    events = [event for event in events if _is_date(event["date"])]
    if days is not None:
        first = today - datetime.timedelta(days=days - 1)
        events = [event for event in events if datetime.date.fromisoformat(event["date"]) >= first]
    order = {"created": 0, "started": 1, "commit": 2, "finding": 3, "closed": 4}
    events.sort(key=lambda event: (event["date"], order.get(event["kind"], 9), event["spec"]), reverse=True)
    return {"days": _days(events, today, days), "events": events}


def _spec_events(spec: dict) -> list[dict]:
    base = {"spec": spec["name"], "title": spec["title"], "repo": ", ".join(spec["repos"])}
    events: list[dict] = []
    if spec["created"]:
        events.append({**base, "date": spec["created"], "kind": "created", "detail": ""})
    if spec["started"]:
        events.append({**base, "date": spec["started"], "kind": "started", "detail": spec["mode"] or ""})
    if spec["closed"]:
        events.append({**base, "date": spec["closed"], "kind": "closed", "detail": _duration(spec)})
    dated = spec["closed"] or spec["started"] or spec["created"]
    if spec["findings"] and dated:
        for line in spec["findings"].splitlines():
            if line.startswith("- "):
                events.append({**base, "date": dated, "kind": "finding", "detail": _finding_title(line[2:])})
    return events


def _duration(spec: dict) -> str:
    start = spec["started"] or spec["created"]
    if not (start and spec["closed"] and _is_date(start) and _is_date(spec["closed"])):
        return ""
    days = (datetime.date.fromisoformat(spec["closed"]) - datetime.date.fromisoformat(start)).days
    label = "working time" if spec["started"] else "lead time"
    if days == 0:
        return f"{label}: same day"
    return f"{label} {days} day{'s' if days != 1 else ''}"


def _finding_title(text: str) -> str:
    text = text.strip()
    if text.startswith("**"):
        end = text.find("**", 2)
        if end > 2:
            return text[2:end].rstrip(".")
    return text.split(". ", 1)[0]


def _repos(folder: Path) -> list[str]:
    toml_path = folder / ATLAS_TOML
    if not toml_path.is_file():
        return []
    try:
        _, declared = read_atlas_toml(toml_path)
    except ValueError:
        return []
    names: list[str] = []
    for name, table in declared.items():
        if judge_source(folder, str(name)) != "ok":
            continue
        nested = declared_repos(table)
        if nested:
            names.extend(f"{name}/{child}" for child in nested)
        else:
            names.append(str(name))
    return names


def _days(events: list[dict], today: datetime.date, days: int | None) -> list[dict]:
    counts: dict[str, int] = {}
    for event in events:
        counts[event["date"]] = counts.get(event["date"], 0) + 1
    if days is None:
        if not counts:
            return []
        first = min(datetime.date.fromisoformat(min(counts)), today)
        last = max(datetime.date.fromisoformat(max(counts)), today)
        span = (last - first).days + 1
        return [{"date": (first + datetime.timedelta(days=offset)).isoformat(),
                 "count": counts.get((first + datetime.timedelta(days=offset)).isoformat(), 0)} for offset in range(span)]
    first = today - datetime.timedelta(days=days - 1)
    return [
        {"date": (first + datetime.timedelta(days=offset)).isoformat(), "count": counts.get((first + datetime.timedelta(days=offset)).isoformat(), 0)}
        for offset in range(days)
    ]


def _is_date(value: str) -> bool:
    try:
        datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return True
