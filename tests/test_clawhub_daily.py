import json
from pathlib import Path

from scripts import clawhub_daily
from scripts.clawhub_daily import apply_comparison, item_from_row, potential_badge, potential_items, render_report, update_dates


def row(slug, name, downloads, stars, author="alice", versions=1):
    return {
        "owner": {"handle": author},
        "skill": {
            "displayName": name,
            "slug": slug,
            "summary": "sample",
            "stats": {
                "downloads": downloads,
                "installsAllTime": downloads // 10,
                "stars": stars,
                "versions": versions,
            },
        },
        "latestVersion": {"version": "1.0.0"},
    }


def test_item_from_row_normalizes_required_fields():
    item = item_from_row(row("gold-pan", "Gold Pan", 100.0, 8.0, "miner", 3.0), 7)
    assert item["rank"] == 7
    assert item["name"] == "Gold Pan"
    assert item["author"] == "miner"
    assert item["slug"] == "gold-pan"
    assert item["downloads"] == 100
    assert item["installs"] == 10
    assert item["stars"] == 8
    assert item["versions"] == 3
    assert item["compare_key"] == "gold-pan"
    assert item["prev_rank"] is None


def test_apply_comparison_marks_strict_daily_and_deltas(tmp_path: Path):
    prev_path = tmp_path / "2026-05-04.json"
    prev = {
        "snapshot_date": "2026-05-04",
        "items": [
            {"rank": 4, "name": "Gold Pan", "author": "miner", "slug": "gold-pan", "compare_key": "gold-pan", "downloads": 100, "stars": 8},
            {"rank": 9, "name": "Dropped", "author": "miner", "slug": "dropped", "compare_key": "dropped", "downloads": 20, "stars": 1},
        ],
    }
    prev_path.write_text(json.dumps(prev), encoding="utf-8")
    items = [item_from_row(row("gold-pan", "Gold Pan", 125, 11), 2)]
    comparison, dropped, limits = apply_comparison(items, prev_path, "2026-05-05")
    assert comparison["strict_daily"] is True
    assert limits == []
    assert items[0]["prev_rank"] == 4
    assert items[0]["download_delta"] == 25
    assert items[0]["star_delta"] == 3
    assert items[0]["rank_change"] == 2
    assert dropped[0]["slug"] == "dropped"


def test_potential_items_requires_history():
    item = item_from_row(row("new", "New", 100, 4), 1)
    assert potential_items([item]) == []


def test_potential_items_includes_new_entry_when_history_exists():
    old = item_from_row(row("old", "Old", 100, 5), 1)
    old["prev_rank"] = 3
    old["rank_change"] = 2
    old["download_delta"] = 10
    old["star_delta"] = 2
    new = item_from_row(row("new", "New", 50, 1), 2)
    potentials = potential_items([old, new])
    by_slug = {item["slug"]: item for item in potentials}
    assert "new" in by_slug
    assert "old" in by_slug
    assert "新进 Top100" in by_slug["new"]["potential_reasons"]


def test_update_dates_keeps_latest_first(tmp_path: Path):
    data_dir = tmp_path / "data"
    update_dates(data_dir, "2026-05-04")
    update_dates(data_dir, "2026-05-06")
    update_dates(data_dir, "2026-05-05")
    payload = json.loads((data_dir / "dates.json").read_text())
    assert payload == {"latest": "2026-05-06", "dates": ["2026-05-06", "2026-05-05", "2026-05-04"]}


def test_report_does_not_call_first_run_new_entries():
    snapshot = {
        "snapshot_date": "2026-05-04",
        "fetched_at": "2026-05-04T00:00:00Z",
        "source": {"pages_succeeded": 4},
        "comparison_basis": {"note": "缺少历史切片，本次不做严格日环比。"},
        "limitations": ["缺少历史切片，本次不做严格日环比。"],
        "items": [item_from_row(row("gold-pan", "Gold Pan", 100, 8), 1)],
    }
    report = render_report(snapshot, [])
    assert "今日无新增潜力skill" in report
    assert "当前排名，历史缺失" in report
    assert "新进，下载 n/a" not in report


def test_resolve_pages_url_defaults_to_github_pages(tmp_path, monkeypatch):
    monkeypatch.delenv("SKILLRUSH_PAGES_URL", raising=False)
    assert clawhub_daily.resolve_pages_url(repo_root=tmp_path) == "https://learnprompt.github.io/skillrush-town/"


def test_resolve_pages_url_reads_cname(tmp_path, monkeypatch):
    monkeypatch.delenv("SKILLRUSH_PAGES_URL", raising=False)
    (tmp_path / "CNAME").write_text("skillrush.goodcase.ai\n", encoding="utf-8")
    assert clawhub_daily.resolve_pages_url(repo_root=tmp_path) == "https://skillrush.goodcase.ai/"


def test_resolve_pages_url_ignores_empty_cname(tmp_path, monkeypatch):
    monkeypatch.delenv("SKILLRUSH_PAGES_URL", raising=False)
    (tmp_path / "CNAME").write_text("\n", encoding="utf-8")
    assert clawhub_daily.resolve_pages_url(repo_root=tmp_path) == clawhub_daily.DEFAULT_PAGES_URL


def test_resolve_pages_url_env_override_wins(tmp_path, monkeypatch):
    (tmp_path / "CNAME").write_text("skillrush.goodcase.ai\n", encoding="utf-8")
    monkeypatch.setenv("SKILLRUSH_PAGES_URL", "https://example.com/town")
    assert clawhub_daily.resolve_pages_url(repo_root=tmp_path) == "https://example.com/town/"


def test_potential_badge_uses_dynamic_date(monkeypatch):
    monkeypatch.setattr(clawhub_daily, "PAGES_URL", "https://learnprompt.github.io/skillrush-town/")
    badge = potential_badge("2026-06-13")
    assert badge == (
        "[![淘金小镇潜力榜](https://img.shields.io/badge/"
        "%E6%B7%98%E9%87%91%E5%B0%8F%E9%95%87%E6%BD%9C%E5%8A%9B%E6%A6%9C-2026--06--13-b4533a)]"
        "(https://learnprompt.github.io/skillrush-town/?date=2026-06-13)"
    )


def test_report_potential_section_includes_badge():
    item = item_from_row(row("riser", "Riser", 500, 9), 2)
    item["prev_rank"] = 12
    item["rank_change"] = 10
    item["download_delta"] = 50
    item["star_delta"] = 3
    snapshot = {
        "snapshot_date": "2026-06-13",
        "fetched_at": "2026-06-13T00:00:00Z",
        "source": {"pages_succeeded": 4},
        "comparison_basis": {"note": "与前一日快照对比。"},
        "limitations": [],
        "items": [item],
    }
    report = render_report(snapshot, [])
    assert "上榜了？把它贴进你的 README" in report
    assert potential_badge("2026-06-13") in report


def test_report_without_potentials_has_no_badge():
    snapshot = {
        "snapshot_date": "2026-05-04",
        "fetched_at": "2026-05-04T00:00:00Z",
        "source": {"pages_succeeded": 4},
        "comparison_basis": {"note": "缺少历史切片，本次不做严格日环比。"},
        "limitations": [],
        "items": [item_from_row(row("gold-pan", "Gold Pan", 100, 8), 1)],
    }
    report = render_report(snapshot, [])
    assert "img.shields.io" not in report


def test_fetch_pages_uses_convex_v4_four_pages_and_cursors(monkeypatch):
    from scripts import clawhub_daily

    calls = []

    def fake_post_json(url, payload, timeout=25):
        calls.append((url, payload, timeout))
        page_no = len(calls)
        return {
            "status": "success",
            "value": {
                "page": [row(f"skill-{page_no}-{index}", f"Skill {page_no}-{index}", 1000 - page_no * 25 - index, 10) for index in range(25)],
                "nextCursor": f"cursor-{page_no}",
            },
        }

    monkeypatch.setattr(clawhub_daily, "post_json", fake_post_json)
    monkeypatch.setattr(clawhub_daily, "diagnostic_api_v1", lambda: {})

    result = clawhub_daily.fetch_pages()

    assert len(calls) == 4
    assert len(result.rows) == 100
    assert result.pages_succeeded == 4
    assert result.limitations == []

    for index, (url, payload, timeout) in enumerate(calls):
        assert url == clawhub_daily.API_URL
        assert timeout == 25
        assert payload["path"] == "skills:listPublicPageV4"
        assert payload["format"] == "json"

        args = payload["args"]
        assert args["sort"] == "downloads"
        assert args["dir"] == "desc"
        assert args["nonSuspiciousOnly"] is True
        assert args["highlightedOnly"] is False
        assert args["numItems"] == 25

        if index == 0:
            assert "cursor" not in args
        else:
            assert args["cursor"] == f"cursor-{index}"
