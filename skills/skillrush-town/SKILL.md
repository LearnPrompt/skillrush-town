---
name: skillrush-town
description: "淘金小镇 | Skillrush Town — 每日 ClawHub Top100 淘金雷达。消费侧触发：用户问「今天 ClawHub 有什么新 skill」「淘金小镇今天有什么」「最近什么 skill 在涨」「有什么潜力 skill 值得装」「ClawHub 榜单」「skill 下载榜 / 增速榜 / 新进榜」时，读取 data/latest.json（或 GitHub Pages 数据）总结 Top10、潜力 Skill 与新进榜。即使用户只是说「帮我看看 skill 圈最近有什么动静」也应该触发。维护侧触发：building, maintaining, forking, or publishing Skillrush Town; tracking ClawHub Top100 downloads snapshots; generating daily Skill reports; evaluating ClawHub source changes; or packaging a public GitHub Pages skill radar. 不要用于：AI 资讯/新闻（用 ai-news-radar）、评估单个信息源是否值得接入（用伯乐）、安装某个具体 skill 本身。"
---

# Skillrush Town

## 消费侧用法（用户只想看榜时）

当用户问"今天有什么新 skill / 什么在涨 / 有什么值得装"这类问题时，不要走维护流程，直接读数据回答：

1. 取数据：仓库内优先读 `data/latest.json`；不在仓库内时读
   `https://learnprompt.github.io/skillrush-town/data/latest.json`。
   回看历史用 `data/snapshots/<YYYY-MM-DD>.json`，可用日期列表在 `data/dates.json`。
2. 总结三块：今日 Top10（`items` 前 10 条）、潜力 Skill（报告
   `data/reports/<date>.md` 的「潜力 Skill」节，或按 SKILL.md 潜力标准从 items 现算）、
   新进榜（有历史时 `prev_rank` 为 null 的条目）。
3. 给出"值得点开看"的 2-3 个，并说清理由（下载/星标增量、排名变化、summary 里的用途），
   附上 `https://learnprompt.github.io/skillrush-town/?date=<snapshot_date>` 方便用户自己看。
4. 诚实转述 `limitations` 与 `comparison_basis.note`：缺历史切片时不要把数字说成日环比。

## First Reads

When this skill triggers inside the repo, read:

- `README.md` for product positioning and user paths.
- `scripts/clawhub_daily.py` before changing data generation.
- `data/dates.json` and the latest `data/snapshots/*.json` before changing the UI.
- `assets/app.js`, `assets/styles.css`, and `index.html` before changing the page.
- `references/source-contract.md` before changing ClawHub request semantics.
- `references/source-adapter-pattern.md` before adding changelog, model leaderboard,
  or any non-ClawHub monitoring source.
- `references/publishing.md` before changing GitHub Pages or Actions.

## Product Direction

Maintain three surfaces:

- **Public town board**: a phone-friendly GitHub Pages site where anyone can
  read the latest ClawHub Top100, growth lists, potential Skills, and history.
- **Forkable Skill generator**: a repo plus Skill that lets users generate their
  own Skill radar without copying private tokens or personal notes.
- **Source-monitoring workflow**: a repeatable pattern for turning public
  leaderboards, changelogs, and release pages into dated snapshots, diffs,
  reports, and optional Agent reminders.

Keep the default story simple: "每天从公开榜单和更新日志里淘出值得看的 AI 变化."
ClawHub Top100 is the first source because it is complex enough to prove the
workflow: runtime request, Convex path, cursor pagination, Top100 normalization,
historical diffs, reports, and a public board.

Do not position this as "just a webpage". The page is the town board; the Skill
is the workflow contract that lets future agents maintain and extend the town.

Good future source examples:

- Claude Code changelog: monitor dated release notes and new capabilities.
- Artificial Analysis model leaderboard: monitor model ranking, price, speed,
  and benchmark changes.
- Other public marketplaces or leaderboards with stable sort and pagination.

## First Run Usage

Installing this Skill only installs the workflow contract; it must not create
hidden scheduled jobs during installation.

For a one-off check, the user can say:

```text
Use skillrush-town to read latest.json and summarize today's ClawHub Top10 and potential Skills.
```

For a daily reminder in Hermes, create a cron job only when the user asks for it.
A good default is 10:00 Asia/Shanghai, after the GitHub Actions update window:

```text
Every day, read https://learnprompt.github.io/skillrush-town/data/latest.json,
summarize the snapshot date, Top10, potential Skills, limitations, and link to
https://learnprompt.github.io/skillrush-town/?date=<snapshot_date>.
```

Codex and Claude Code are usually task runners, not persistent reminder daemons.
For them, keep the repo forkable and use GitHub Actions, system cron, or Hermes
cron for notifications.

## Source Rules

### Default ClawHub Source

- The canonical ranking source is Convex `api/query`, path
  `skills:listPublicPageV4`.
- Request args must keep `sort=downloads`, `dir=desc`,
  `nonSuspiciousOnly=true`, `highlightedOnly=false`, `numItems=25`.
- Build Top100 by following `nextCursor` for 4 pages.
- Do not use `GET /api/v1/skills` as the primary ranking basis.
- If API fields, path, or pagination change, write the limitation into both
  snapshot and report.

### Adding New Sources

Before adding a changelog, model leaderboard, release feed, or any non-ClawHub
source, read `references/source-adapter-pattern.md` and create a source-specific
contract file:

```text
skills/skillrush-town/references/source-contract-<source>.md
```

Do not merge a new source adapter unless it has:

- a canonical URL or request contract
- stable item or entry keys
- snapshot schema
- diff semantics
- limitation handling
- headless tests with fixtures or mocked network responses

## Daily Report Rules

Every run must produce:

- `data/snapshots/YYYY-MM-DD.json`
- `data/reports/YYYY-MM-DD.md`
- `data/latest.json`
- `data/dates.json`

Reports must include new entries, dropped entries, Top10 changes, downloads
growth Top10, stars growth Top10, and potential Skills. If there is no potential
Skill, explicitly write `今日无新增潜力skill`.

Never describe the first run, migration run, or missing-history comparison as a
strict daily delta.

## Potential Skill Criteria

Include at most 10. A Skill qualifies if any condition is true:

- new Top100 entry
- download delta Top20 and star delta Top30
- rank rises by at least 8 places

Each potential Skill needs name, rank change, download/star delta, and one short
recommendation.

## Writing Style

For public README and release text, keep the town/gold-rush metaphor but avoid
AI-marketing boilerplate. Prefer concrete use cases over abstract claims. Do not
say "empower", "ecosystem flywheel", "comprehensive platform", or similar filler.

## Validate

### Required Headless Validation

These checks must work without Chrome, Playwright, Puppeteer, Camofox, Selenium,
or browser login state:

```bash
python -m py_compile scripts/clawhub_daily.py
python -m pytest -q
python "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" skills/skillrush-town
```

For a live ingestion check, write into a temporary data directory instead of
mutating committed data:

```bash
TMP=$(mktemp -d)
python scripts/clawhub_daily.py --date 2026-05-04 --data-dir "$TMP/data"
```

### Optional Browser / Manual Page Check

Only run this when a browser is available:

```bash
python3 -m http.server 8093
```

Open `http://127.0.0.1:8093/?date=2026-05-04` and verify the date selector,
Top10, limitation panel, potential Skill section, search, and Top100 table.

