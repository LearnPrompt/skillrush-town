#!/usr/bin/env python3
"""Generate an Atom feed (feed.xml) from daily snapshots. Stdlib only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from scripts.clawhub_daily import potential_items, resolve_pages_url
except ImportError:  # run as `python scripts/generate_feed.py` from repo root
    from clawhub_daily import potential_items, resolve_pages_url

ATOM_NS = "http://www.w3.org/2005/Atom"
PAGES_URL = resolve_pages_url()
FEED_TITLE = "淘金小镇日报"
DEFAULT_MAX_ENTRIES = 14


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def entry_summary(snapshot: dict) -> str:
    items = snapshot.get("items") or []
    top3 = items[:3]
    potentials = potential_items(items)
    lines = ["今日 Top3："]
    for item in top3:
        lines.append(f"#{item['rank']} {item['name']}（{item['author']} / {item['slug']}）")
    lines.append(f"潜力 Skill：{len(potentials)} 个。")
    note = (snapshot.get("comparison_basis") or {}).get("note")
    if note:
        lines.append(note)
    return "\n".join(lines)


def snapshot_updated(snapshot: dict, snapshot_date: str) -> str:
    fetched = snapshot.get("fetched_at")
    if isinstance(fetched, str) and fetched:
        return fetched
    return f"{snapshot_date}T00:00:00Z"


def build_feed(data_dir: Path, max_entries: int = DEFAULT_MAX_ENTRIES) -> ET.Element:
    dates_payload = read_json(data_dir / "dates.json")
    dates = (dates_payload.get("dates") or [])[:max_entries]

    ET.register_namespace("", ATOM_NS)
    feed = ET.Element(f"{{{ATOM_NS}}}feed")
    ET.SubElement(feed, f"{{{ATOM_NS}}}title").text = FEED_TITLE
    ET.SubElement(feed, f"{{{ATOM_NS}}}id").text = PAGES_URL
    ET.SubElement(feed, f"{{{ATOM_NS}}}link", {"href": PAGES_URL, "rel": "alternate"})
    ET.SubElement(feed, f"{{{ATOM_NS}}}link", {"href": f"{PAGES_URL}feed.xml", "rel": "self"})
    ET.SubElement(feed, f"{{{ATOM_NS}}}subtitle").text = "每天从 ClawHub 下载榜 Top100 里，淘出新进榜、增速榜和潜力 Skill。"
    author = ET.SubElement(feed, f"{{{ATOM_NS}}}author")
    ET.SubElement(author, f"{{{ATOM_NS}}}name").text = "LearnPrompt"

    feed_updated = None
    for snapshot_date in dates:
        snapshot_path = data_dir / "snapshots" / f"{snapshot_date}.json"
        if not snapshot_path.exists():
            continue
        snapshot = read_json(snapshot_path)
        updated = snapshot_updated(snapshot, snapshot_date)
        if feed_updated is None:
            feed_updated = updated
        entry_url = f"{PAGES_URL}?date={snapshot_date}"
        entry = ET.SubElement(feed, f"{{{ATOM_NS}}}entry")
        ET.SubElement(entry, f"{{{ATOM_NS}}}title").text = f"淘金小镇日报 {snapshot_date}"
        ET.SubElement(entry, f"{{{ATOM_NS}}}id").text = entry_url
        ET.SubElement(entry, f"{{{ATOM_NS}}}link", {"href": entry_url, "rel": "alternate"})
        ET.SubElement(entry, f"{{{ATOM_NS}}}updated").text = updated
        ET.SubElement(entry, f"{{{ATOM_NS}}}content", {"type": "text"}).text = entry_summary(snapshot)

    updated_el = ET.Element(f"{{{ATOM_NS}}}updated")
    updated_el.text = feed_updated or "1970-01-01T00:00:00Z"
    feed.insert(2, updated_el)
    return feed


def write_feed(data_dir: Path, output: Path, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
    feed = build_feed(data_dir, max_entries)
    ET.indent(feed)
    payload = ET.tostring(feed, encoding="unicode", xml_declaration=True)
    output.write_text(payload + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data", help="Data directory containing dates.json and snapshots/")
    parser.add_argument("--output", default="feed.xml", help="Output feed path")
    parser.add_argument("--max-entries", type=int, default=DEFAULT_MAX_ENTRIES)
    args = parser.parse_args()

    write_feed(Path(args.data_dir), Path(args.output), args.max_entries)
    print(json.dumps({"feed": args.output, "max_entries": args.max_entries}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
