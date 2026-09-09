#!/usr/bin/env python3
"""Fetch ClawHub downloads Top100 and generate static site data."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SOURCE_URL = "https://clawhub.ai/skills?sort=downloads&nonSuspicious=true"
API_URL = "https://wry-manatee-359.convex.cloud/api/query"
API_PATH = "skills:listPublicPageV4"
BASE_ARGS = {
    "sort": "downloads",
    "dir": "desc",
    "nonSuspiciousOnly": True,
    "highlightedOnly": False,
    "numItems": 25,
}
DIAGNOSTIC_URL = "https://clawhub.ai/api/v1/skills?sort=downloads&nonSuspicious=true"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def number(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    except (TypeError, ValueError):
        return None


def post_json(url: str, payload: dict[str, Any], timeout: int = 25) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, timeout: int = 15) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def item_from_row(row: dict[str, Any], rank: int) -> dict[str, Any]:
    skill = row.get("skill") or row
    owner = row.get("owner") or {}
    stats = skill.get("stats") or {}
    latest = row.get("latestVersion") or skill.get("latestVersion") or {}
    name = skill.get("displayName") or skill.get("name") or skill.get("slug") or "Unknown"
    author = owner.get("handle") or owner.get("displayName") or row.get("ownerHandle") or skill.get("ownerHandle") or "Unknown"
    slug = skill.get("slug") or ""
    compare_key = slug or f"{author}/{name}".lower()

    return {
        "rank": rank,
        "name": name,
        "author": author,
        "slug": slug,
        "downloads_raw": stats.get("downloads"),
        "downloads": number(stats.get("downloads")),
        "installs_raw": stats.get("installsAllTime", stats.get("installsCurrent")),
        "installs": number(stats.get("installsAllTime", stats.get("installsCurrent"))),
        "stars_raw": stats.get("stars"),
        "stars": number(stats.get("stars")),
        "versions": number(stats.get("versions")),
        "latest_version": latest.get("version"),
        "summary": skill.get("summary"),
        "compare_key": compare_key,
        "prev_rank": None,
        "download_delta": None,
        "star_delta": None,
        "rank_change": None,
    }


@dataclass
class FetchResult:
    rows: list[dict[str, Any]]
    pages_succeeded: int
    limitations: list[str]
    diagnostics: dict[str, Any]


def diagnostic_api_v1() -> dict[str, Any]:
    try:
        payload = get_json(DIAGNOSTIC_URL)
        items = payload.get("items") if isinstance(payload, dict) else None
        return {
            "url": DIAGNOSTIC_URL,
            "role": "diagnostic_only_not_comparison_basis",
            "items_count": len(items) if isinstance(items, list) else None,
            "known_empty_semantics": "If this endpoint returns empty items, treat it as a known non-primary API view, not as no public ranking.",
        }
    except Exception as exc:  # pragma: no cover - network diagnostic should not fail the run
        return {
            "url": DIAGNOSTIC_URL,
            "role": "diagnostic_only_not_comparison_basis",
            "error": repr(exc),
        }


def fetch_pages() -> FetchResult:
    limitations: list[str] = []
    rows: list[dict[str, Any]] = []
    pages_succeeded = 0
    next_cursor: str | None = None

    for page_no in range(1, 5):
        args = dict(BASE_ARGS)
        if next_cursor:
            args["cursor"] = next_cursor
        payload = {"path": API_PATH, "args": args, "format": "json"}
        try:
            data = post_json(API_URL, payload)
        except Exception as exc:
            limitations.append(f"分页失败：第 {page_no} 页请求失败：{exc!r}")
            break

        if data.get("status") != "success":
            limitations.append(f"分页失败：第 {page_no} 页 status={data.get('status')} error={data.get('error')}")
            break

        value = data.get("value") or {}
        page = value.get("page") or []
        if not isinstance(page, list):
            limitations.append(f"接口字段变化：第 {page_no} 页 value.page 不是 list")
            break

        rows.extend(page)
        pages_succeeded += 1
        next_cursor = value.get("nextCursor")
        if page_no < 4 and not next_cursor:
            limitations.append(f"分页限制：第 {page_no} 页缺少 nextCursor，未能继续拼满 Top100")
            break

    if len(rows) < 100:
        limitations.append(f"Top100 不完整：本次只得到 {len(rows)} 条")

    return FetchResult(rows=rows[:100], pages_succeeded=pages_succeeded, limitations=limitations, diagnostics={"get_api_v1_skills": diagnostic_api_v1()})


def nearest_previous_snapshot(snapshot_dir: Path, snapshot_date: str) -> Path | None:
    candidates = sorted(path for path in snapshot_dir.glob("*.json") if path.stem < snapshot_date)
    return candidates[-1] if candidates else None


def apply_comparison(items: list[dict[str, Any]], prev_path: Path | None, snapshot_date: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    limitations: list[str] = []
    dropped: list[dict[str, Any]] = []
    if not prev_path:
        limitations.append("缺少历史切片，本次不做严格日环比。")
        return {
            "previous_snapshot": None,
            "strict_daily": False,
            "note": "缺少历史切片，本次不做严格日环比。",
        }, dropped, limitations

    prev = read_json(prev_path)
    prev_items = prev.get("items") or []
    prev_by_key = {item.get("compare_key"): item for item in prev_items if item.get("compare_key")}
    current_keys = {item["compare_key"] for item in items}

    for item in items:
        old = prev_by_key.get(item["compare_key"])
        if not old:
            continue
        item["prev_rank"] = old.get("rank")
        if item.get("downloads") is not None and old.get("downloads") is not None:
            item["download_delta"] = item["downloads"] - old["downloads"]
        if item.get("stars") is not None and old.get("stars") is not None:
            item["star_delta"] = item["stars"] - old["stars"]
        if item["prev_rank"] is not None:
            item["rank_change"] = item["prev_rank"] - item["rank"]

    for key, old in prev_by_key.items():
        if key not in current_keys:
            dropped.append(old)

    previous_day = (date.fromisoformat(snapshot_date) - timedelta(days=1)).isoformat()
    strict_daily = prev.get("snapshot_date") == previous_day
    if strict_daily:
        note = f"与前一日快照 {prev_path.name} 对比。"
    else:
        note = f"与最近历史快照 {prev_path.name} 对比，不是严格日环比。"
        limitations.append("缺少前一日快照，差分不是严格 24 小时日环比。")

    return {
        "previous_snapshot": str(prev_path),
        "strict_daily": strict_daily,
        "note": note,
    }, dropped, limitations


def top_by(items: list[dict[str, Any]], field: str, limit: int) -> list[dict[str, Any]]:
    valid = [item for item in items if isinstance(item.get(field), int)]
    return sorted(valid, key=lambda item: (-item[field], item["rank"]))[:limit]


def potential_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has_history = any(item.get("prev_rank") is not None for item in items)
    if not has_history:
        return []

    download_top20 = {item["compare_key"] for item in top_by(items, "download_delta", 20)}
    star_top30 = {item["compare_key"] for item in top_by(items, "star_delta", 30)}
    out: list[dict[str, Any]] = []
    for item in items:
        reasons: list[str] = []
        if item.get("prev_rank") is None:
            reasons.append("新进 Top100")
        if item["compare_key"] in download_top20 and item["compare_key"] in star_top30:
            reasons.append("下载增量 Top20 且星标增量 Top30")
        if isinstance(item.get("rank_change"), int) and item["rank_change"] >= 8:
            reasons.append("排名上升 >= 8 位")
        if reasons:
            row = dict(item)
            row["potential_reasons"] = reasons
            out.append(row)
    return sorted(out, key=lambda item: item["rank"])[:10]


def fmt_delta(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"+{value}" if value > 0 else str(value)


def line_for_item(item: dict[str, Any]) -> str:
    prev_rank = item.get("prev_rank")
    if prev_rank is None:
        return f"- #{item['rank']} {item['name']}（{item['author']} / `{item['slug']}`）：当前排名，历史缺失，下载 {fmt_delta(item.get('download_delta'))}，星标 {fmt_delta(item.get('star_delta'))}"
    else:
        move = f"{prev_rank} -> {item['rank']}"
    return f"- #{item['rank']} {item['name']}（{item['author']} / `{item['slug']}`）：排名 {move}，下载 {fmt_delta(item.get('download_delta'))}，星标 {fmt_delta(item.get('star_delta'))}"


DEFAULT_PAGES_URL = "https://learnprompt.github.io/skillrush-town/"


def resolve_pages_url(repo_root: Path | None = None) -> str:
    """Site base URL: SKILLRUSH_PAGES_URL env > repo-root CNAME > GitHub Pages default."""
    override = os.environ.get("SKILLRUSH_PAGES_URL", "").strip()
    if override:
        return override if override.endswith("/") else override + "/"
    root = repo_root if repo_root is not None else Path(__file__).resolve().parent.parent
    cname = root / "CNAME"
    if cname.is_file():
        lines = [line.strip() for line in cname.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            return f"https://{lines[0]}/"
    return DEFAULT_PAGES_URL


PAGES_URL = resolve_pages_url()


def potential_badge(snapshot_date: str) -> str:
    """Markdown badge for potential-list entries, date is dynamic."""
    shield_date = snapshot_date.replace("-", "--")
    return (
        "[![淘金小镇潜力榜](https://img.shields.io/badge/"
        f"%E6%B7%98%E9%87%91%E5%B0%8F%E9%95%87%E6%BD%9C%E5%8A%9B%E6%A6%9C-{shield_date}-b4533a)]"
        f"({PAGES_URL}?date={snapshot_date})"
    )


def render_report(snapshot: dict[str, Any], dropped: list[dict[str, Any]]) -> str:
    items = snapshot["items"]
    lines: list[str] = [
        f"# ClawHub 日报 {snapshot['snapshot_date']}",
        "",
        "## 抓取状态",
        "",
        f"- 抓取时间：`{snapshot['fetched_at']}`",
        f"- 主榜单接口：`POST {API_URL}`",
        f"- Convex path：`{API_PATH}`",
        f"- 成功页数：{snapshot['source']['pages_succeeded']}/4",
        f"- 本次条目：{len(items)}",
        f"- 对比口径：{snapshot['comparison_basis']['note']}",
        "",
        "## 限制说明",
        "",
    ]

    if snapshot.get("limitations"):
        lines.extend(f"- {item}" for item in snapshot["limitations"])
    else:
        lines.append("- 暂无已知限制。")
    lines.append("- `GET /api/v1/skills` 仅作诊断，不作为主榜单接口；若它返回空 `items`，不代表页面无榜单。")

    lines += ["", "## 新进榜", ""]
    has_history = any(item.get("prev_rank") is not None for item in items)
    new_entries = [item for item in items if has_history and item.get("prev_rank") is None]
    new_empty = "- 今日无新进榜。" if has_history else "- 无，或因缺少历史切片无法判断。"
    lines.extend([line_for_item(item) for item in new_entries[:20]] or [new_empty])

    lines += ["", "## 掉榜", ""]
    dropped_empty = "- 今日无掉榜。" if has_history else "- 无，或因缺少历史切片无法判断。"
    lines.extend([f"- 原 #{item.get('rank')} {item.get('name')}（{item.get('author')} / `{item.get('slug')}`）" for item in dropped[:20]] or [dropped_empty])

    lines += ["", "## Top10 变动", ""]
    lines.extend(line_for_item(item) for item in items[:10])

    lines += ["", "## 下载增速 Top10", ""]
    lines.extend([line_for_item(item) for item in top_by(items, "download_delta", 10)] or ["- 缺少历史切片，无法计算下载增速。"])

    lines += ["", "## 星标增速 Top10", ""]
    lines.extend([line_for_item(item) for item in top_by(items, "star_delta", 10)] or ["- 缺少历史切片，无法计算星标增速。"])

    lines += ["", "## 潜力 Skill", ""]
    potentials = potential_items(items)
    if not potentials:
        lines.append("今日无新增潜力skill")
    else:
        for item in potentials:
            lines += [
                f"### #{item['rank']} {item['name']}",
                f"- 作者：{item['author']}",
                f"- slug：`{item['slug']}`",
                f"- 命中原因：{'；'.join(item['potential_reasons'])}",
                f"- 排名变化：{('新进' if item.get('prev_rank') is None else str(item.get('prev_rank')) + ' -> ' + str(item.get('rank')))}",
                f"- 下载增量：{fmt_delta(item.get('download_delta'))}",
                f"- 星标增量：{fmt_delta(item.get('star_delta'))}",
                "- 建议：先看 README、权限范围和最近版本，再决定要不要试用。",
                "- 上榜了？把它贴进你的 README：",
                "",
                "  ```markdown",
                f"  {potential_badge(snapshot['snapshot_date'])}",
                "  ```",
                "",
            ]
    return "\n".join(lines) + "\n"


def update_dates(data_dir: Path, snapshot_date: str) -> None:
    dates_path = data_dir / "dates.json"
    if dates_path.exists():
        payload = read_json(dates_path)
        dates = payload.get("dates") or []
    else:
        dates = []
    if snapshot_date not in dates:
        dates.append(snapshot_date)
    dates = sorted(set(dates), reverse=True)
    write_json(dates_path, {"latest": dates[0], "dates": dates})


def build_snapshot(snapshot_date: str, data_dir: Path) -> dict[str, Any]:
    result = fetch_pages()
    items = [item_from_row(row, rank) for rank, row in enumerate(result.rows, 1)]
    comparison, dropped, comparison_limits = apply_comparison(items, nearest_previous_snapshot(data_dir / "snapshots", snapshot_date), snapshot_date)
    limitations = [*result.limitations, *comparison_limits]
    snapshot = {
        "snapshot_date": snapshot_date,
        "fetched_at": utc_now(),
        "source": {
            "url": SOURCE_URL,
            "api": API_URL,
            "path": API_PATH,
            "args": BASE_ARGS,
            "page_size": 25,
            "pages_requested": 4,
            "pages_succeeded": result.pages_succeeded,
            "diagnostics": result.diagnostics,
        },
        "comparison_basis": {
            "primary_ranking": "POST Convex api/query path=skills:listPublicPageV4 sort=downloads dir=desc nonSuspiciousOnly=true highlightedOnly=false numItems=25, first 4 pages by nextCursor.",
            "compare_key": "slug, fallback author/name",
            **comparison,
        },
        "limitations": limitations,
        "dropped_items": dropped,
        "items": items,
    }
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(), help="Snapshot date, YYYY-MM-DD")
    parser.add_argument("--data-dir", default="data", help="Output data directory")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    snapshot = build_snapshot(args.date, data_dir)
    snapshot_path = data_dir / "snapshots" / f"{args.date}.json"
    report_path = data_dir / "reports" / f"{args.date}.md"
    write_json(snapshot_path, snapshot)
    write_json(data_dir / "latest.json", snapshot)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(snapshot, snapshot.get("dropped_items") or []), encoding="utf-8")
    update_dates(data_dir, args.date)
    print(json.dumps({"snapshot": str(snapshot_path), "report": str(report_path), "items": len(snapshot["items"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
