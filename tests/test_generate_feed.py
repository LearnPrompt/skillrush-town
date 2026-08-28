import json
from pathlib import Path
from xml.etree import ElementTree as ET

from scripts import generate_feed
from scripts.generate_feed import build_feed, write_feed

ATOM = "{http://www.w3.org/2005/Atom}"


def make_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    (data_dir / "snapshots").mkdir(parents=True)
    (data_dir / "dates.json").write_text(
        json.dumps({"latest": "2026-06-12", "dates": ["2026-06-12", "2026-06-11"]}),
        encoding="utf-8",
    )
    for day, fetched in (("2026-06-12", "2026-06-12T06:15:36Z"), ("2026-06-11", "2026-06-11T06:10:00Z")):
        snapshot = {
            "snapshot_date": day,
            "fetched_at": fetched,
            "comparison_basis": {"note": "与前一日快照对比。"},
            "items": [
                {"rank": rank, "name": f"Skill {rank}", "author": "alice", "slug": f"skill-{rank}", "compare_key": f"skill-{rank}", "prev_rank": rank, "download_delta": 10, "star_delta": 1, "rank_change": 0}
                for rank in range(1, 5)
            ],
        }
        (data_dir / "snapshots" / f"{day}.json").write_text(json.dumps(snapshot), encoding="utf-8")
    return data_dir


def test_build_feed_one_entry_per_day(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(generate_feed, "PAGES_URL", "https://learnprompt.github.io/skillrush-town/")
    feed = build_feed(make_data_dir(tmp_path))
    entries = feed.findall(f"{ATOM}entry")
    assert len(entries) == 2
    titles = [entry.findtext(f"{ATOM}title") for entry in entries]
    assert titles == ["淘金小镇日报 2026-06-12", "淘金小镇日报 2026-06-11"]
    first = entries[0]
    assert first.find(f"{ATOM}link").get("href") == "https://learnprompt.github.io/skillrush-town/?date=2026-06-12"
    content = first.findtext(f"{ATOM}content")
    assert "今日 Top3：" in content
    assert "#1 Skill 1" in content
    assert "潜力 Skill：" in content
    assert feed.findtext(f"{ATOM}updated") == "2026-06-12T06:15:36Z"


def test_write_feed_outputs_valid_xml(tmp_path: Path):
    output = tmp_path / "feed.xml"
    write_feed(make_data_dir(tmp_path), output)
    parsed = ET.parse(output)
    assert parsed.getroot().tag == f"{ATOM}feed"
    assert parsed.getroot().findtext(f"{ATOM}title") == "淘金小镇日报"


def test_build_feed_skips_missing_snapshots(tmp_path: Path):
    data_dir = make_data_dir(tmp_path)
    (data_dir / "snapshots" / "2026-06-11.json").unlink()
    feed = build_feed(data_dir)
    assert len(feed.findall(f"{ATOM}entry")) == 1
