# HST Intelligence — Plan

A weekly research platform for **heat shrink tubing** — products, materials, manufacturing,
characterization, standards, and applications — built on the SoftRobotics Intelligence pipeline
architecture and re-targeted to HST using the topic areas, search queries, and source lists from the
*Heat Shrink Tubing Intelligence Agent* setup guide
(`/Users/lele/Le_Documents/AI/hst_agent/HST_Agent_Setup_Guide.docx`).

This document is the build spec. No code exists yet; Steps 1–8 below are the work.

## Why this, and not the existing agent

The previous HST agent (`/Users/lele/Le_Documents/AI/hst_agent`, now retired — see Open items) is a
single `agent.py` that ran 8 live web searches on a Monday routine and emitted a Word doc + PPTX to a
private repo. It has no
archive, no deduplication, no scoring, and no way to see the week without opening a document — every
week starts from zero, and nothing accumulates.

The SoftRobotics Intelligence architecture (`/Users/lele/Le_Documents/TE/SoftRobotic`) fixes exactly
that: a config-driven pipeline with a persistent SQLite archive, LLM relevance scoring, novelty
dedup against a rolling memory, and a browsable static site. Everything domain-specific lives in
`targeting.yaml` and `prompts/`, so re-targeting it to HST is mostly configuration, not new code.

### Decisions

| | |
|---|---|
| **Weekly web-search sections** | **Materials** + **Notable Products** + **Regulatory Watch** — all three stored in SQLite and rendered as site pages. Materials is SoftRobotic's Material Requirements page re-targeted to HST; the other two are new. SoftRobotic's off-site jobs doc is dropped. |
| **Publishing** | Public repo + GitHub Pages, same as SoftRobotic. Repo `LeMa-3254/HST-development-tracker` → `https://lema-3254.github.io/HST-development-tracker/`. |
| **Schedule** | Tuesday 8:00 AM PDT → `cron: "0 15 * * 2"`. |
| **Deliverables** | Site only — no Word doc, no PPTX. `pipeline/jobs_doc.py`, `prompts/jobs.md`, `python-docx`, the `output/` dir, and the artifact-upload workflow step are all dropped. |

---

## Architecture (inherited from SoftRobotics Intelligence)

Ingest public sources → keyword gate → LLM relevance/quality scoring (0–100) → enrichment (summary +
why-it-matters) → local-embedding dedup (fastembed / ONNX, no PyTorch) against a 30-day memory →
SQLite archive → static GitHub Pages site (feed + archive + weekly synthesis + three section pages).
Config-driven via `targeting.yaml`; only the Anthropic API key is required.

The pipeline degrades rather than fails: with no `ANTHROPIC_API_KEY` it falls back to keyword
bootstrap scoring and skips the three web-search sections, and still runs end to end.

---

## Domain adaptations

### Gate — two-axis (differs from SoftRobotic)

SoftRobotic uses a **single-axis** gate: one robotics term and an item is a candidate. Copying that
shape here would mean gating on "heat shrink" — a far narrower phrase than "robot". Most weeks would
surface two or three items, and genuinely relevant work (FEP extrusion, e-beam crosslinking
chemistry, PFAS restrictions on fluoropolymers) rarely uses the phrase at all. Gating on the broad
polymer vocabulary instead would drown the feed.

So the gate is two-axis, closer to the original Polymind design. Three vocabulary lists:

- **`hst_core_terms`** — direct anchors; any single hit qualifies an item outright:
  heat shrink / heat-shrink / heatshrink, shrink tubing, shrinkable tubing, shrink sleeve, dual-wall
  tubing, adhesive-lined tubing, cross-linked polyolefin, radiation cross-linking, e-beam
  crosslinking, expansion ratio, Raychem.
- **`adjacent_terms`** — polymer / process / property vocabulary: fluoropolymer, PTFE, FEP, PFA,
  PVDF, PEEK, polyolefin, PFAS, PFAS-free, shape-memory polymer, gel fraction, crosslink density,
  irradiation dose, extrusion, twin-screw compounding, dielectric strength, thermal aging, flame
  retardant.
- **`context_terms`** — where HST actually lives: wire, cable, wire harness, cable jacket,
  insulation, sleeving, splice, connector, terminal, catheter shaft, implantable lead, busbar, EMI
  shielding, battery pack.

**Rule:** `core` **OR** (`adjacent` **AND** `context`).

Excludes stay conservative — shrink-wrap packaging, shrinkflation, stock market, cryptocurrency. The
LLM rubric is the real filter; the keyword gate just saves tokens on obvious noise.

`technical_boost_terms` raise the score and act as the secondary candidate sort. **Revised at build
time:** the guide's characterization vocabulary (DMA, DSC, TGA, FTIR, SEM/EDX, tensile, Instron) was
dropped — it appears in essentially every polymer paper, so it correlated with "this is an academic
abstract" rather than with heat shrink tubing, handing journal items a permanent boost that carried
no relevance signal. What remains correlates specifically with HST: the named standards a tubing
product is qualified to (UL 224, MIL-I-23053, IEC 60684, SAE AS23053, ISO 6722, ASTM D2671, RoHS,
REACH) and the parameters unique to a shrinkable product (shrink/expansion ratio, recovery
temperature, continuous use temperature, recovered wall thickness, gel fraction, irradiation dose,
dual-wall, adhesive liner, PFAS-free).

### Themes (8)

The guide's 8 topic areas become the fixed taxonomy — the scoring model must tag every kept item with
exactly one label (or `Other`):

`Products & Launches` · `Materials & Formulations` · `Manufacturing & Processing` ·
`Characterization & Testing` · `Standards & Regulatory` · `Applications` · `Market & Supply Chain` ·
`Academic R&D`

### Three weekly sections (LLM web search)

These need live web knowledge rather than RSS, so they use the Anthropic server-side `web_search`
tool on the `--weekly-synthesis` path. All three are stored in SQLite and rendered on the site.

- **Materials** (`materials.html`) — what materials go into heat shrink tubing, and for what. Rows
  keyed by tubing family / end use → base polymer + crosslinking route → numeric property targets →
  open challenge.
- **Notable Products** (`products.html`) — real launches from TE/Raychem, 3M, HellermannTyton, Alpha
  Wire, Zeus, DSG-Canusa, Cobalt.
- **Regulatory Watch** (`regulatory.html`) — UL 224, MIL-I-23053, IEC 60684, SAE AS23053, ISO 6722,
  EPA/ECHA PFAS actions, RoHS/WEEE, FDA medical-grade guidance, each with its impact on a tubing
  manufacturer.

Regulatory Watch is doing real work, not decoration: the standards bodies and regulators have no
reliable RSS, so this section is the only path by which their activity reaches the site.

---

## Sources

Same six adapters, re-pointed.

| Adapter | Target |
|---|---|
| `arxiv` | `cond-mat.mtrl-sci`, `cond-mat.soft`, `physics.app-ph` — radiation effects on polymers, crosslinking chemistry, shape-memory polymers |
| `openalex` / `crossref` | heat shrink tubing, crosslinked polyolefin, radiation crosslinking, fluoropolymer tubing, shape-memory polymer, wire & cable insulation |
| `journal_rss` | **Disabled at build time** — feeds are live but serve bibliographic metadata instead of abstracts, so nothing passes the gate; the same journals are covered via Crossref/OpenAlex. See IMPLEMENTATION_STATUS.md |
| `web_news` | trade press — see below |
| `company_news` | manufacturer newsrooms — **new group**, see below |
| `google_news` | the guide's 8 topic queries + widened company set + regulator queries |

### Feed probe results

These were checked live and should not need re-probing. Everything in the "dead" list below belongs in
`disabled_feeds` **with its reason recorded**, so it isn't rediscovered in six months.

**Live — use these:**

| Feed | URL |
|---|---|
| PlasticsToday | `https://www.plasticstoday.com/rss.xml` |
| Plastics Technology | `https://www.ptonline.com/rss/articles` |
| Medical Design & Outsourcing | `https://www.medicaldesignandoutsourcing.com/feed/` |
| Wire & Cable Technology Intl | `https://wiretech.com/feed/` |
| IWCS | `https://iwcs.org/feed/` |
| **3M** (press releases) | `https://news.3m.com/press-releases?pagetemplate=rss` |
| **Zeus Company** | `https://www.zeusinc.com/feed/` |
| **Mattr** (DSG-Canusa parent) | `https://www.mattr.com/feed/` |

Note the 3M URL: the obvious `/rss` and `/rss/all-news` paths return HTML, not a feed. Only the
`?pagetemplate=rss` query form works.

**Dead — record and route via Google News instead:**

TE Connectivity (`te.com/en/rss/news.xml` → 403, blocks non-browser agents) · HellermannTyton (404) ·
Alpha Wire (404) · Panduit (404) · Sumitomo Electric (404) · Molex, Nitto Denko, Junkosha (no
response) · Nordson MEDICAL (403) · Digi-Key new products (403, Cloudflare) · C&EN (both
`cen.acs.org/rss/all.xml` and `/rss/materials.xml` 404) · ACS journal feeds (403 from CI, per
SoftRobotic's existing note).

**Caveat:** the probe ran from a home IP. CI runners get blocked differently, so the 403s in
particular may behave differently on GitHub Actions. Treat the first live run's error log as the real
verdict.

**Implementation note:** `mattr.com/feed/` returned gzip-encoded bytes even with no `Accept-Encoding`
request header. `fetch_url` in `sources/base.py` does a plain `.read()` with no decompression — if
the first run logs a parse error there, add a gzip-magic-byte (`\x1f\x8b`) fallback. About four
lines, and it hardens every other feed too.

### Google News queries

The manufacturers announce SKUs on their own newsrooms before trade press picks them up, but most
have no feed — so the company set is deliberately wide. The guide's seven (TE Connectivity/Raychem,
3M, HellermannTyton, Alpha Wire, Zeus, DSG-Canusa, Cobalt) extend to the rest of the vendor landscape
shipping heat shrink or the fluoropolymer tubing feeding it: Sumitomo Electric (Sumitube), Molex,
Panduit, Nitto Denko, Junkosha, Chukoh Chemical, Insultab, Qualtek, Gremtek, Parker Chomerics, and
the medical-tubing extruders (Nordson MEDICAL, Putnam Plastics, Optinova, Advanced Polymers, Teleflex
Medical OEM).

Phrase these as **launch-shaped** queries — `"Zeus heat shrink tubing"`, `"Sumitomo heat shrink new
product"` — not bare company names, so the query filters before the gate sees the item.

Plus the guide's 8 topic queries verbatim, standards/regulator queries (UL 224, MIL-I-23053, EPA
PFAS, ECHA REACH PFAS, SAE AS23053, FDA medical tubing), and the trade-show windows where launches
cluster: Wire Düsseldorf, IWCS, MD&M West, productronica.

**Cost consequence:** raise `scoring.max_candidates` from SoftRobotic's 200 to **250**. The prefilter
in `pipeline/run.py` already sorts technical-first then by recency before truncating, so the cap drops
the weakest Google News noise rather than real product news. Watch `candidates` vs `scored` in the
`runs` table on the first live run — if candidates routinely slam the cap, tighten queries before
raising it further.

---

## Build steps

### 1. Copy the SoftRobotic scaffold, stripped of instance state

Copy `config.py`, `models.py`, `Makefile`, `pyproject.toml`, `requirements.txt`, `.env.example`,
`.gitignore`, and the `pipeline/ sources/ store/ site/ prompts/ tests/ .github/workflows/`
directories.

Do **not** copy `.git/`, `.venv/`, `data/tracker.db`, `__pycache__/`, `.env`, `output/`.

Carries over verbatim (domain-neutral): `config.py`, `models.py`,
`pipeline/{ingest,dedup,embeddings,model_clients,enrich,synth}.py`,
`sources/{arxiv,openalex,crossref,journal_rss,rss_feeds,google_news}.py`, `store/db.py`,
`.github/workflows/claude*.yml`.

Delete after copying: `pipeline/jobs_doc.py`, `prompts/jobs.md`. Keep
`prompts/material_requirements.md` — it gets rewritten in Step 4, not deleted. Remove `python-docx`
from `requirements.txt` / `pyproject.toml` and the `output/` entry from `.gitignore`.

### 2. `targeting.yaml` — full rewrite

The main work. Site identity (`HST Intelligence`, tagline *"Heat shrink tubing R&D, materials, and
regulatory intelligence"*, `feed_days: 30`, `max_age_days: 30`, `lookback_hours: 168`), the three
vocabulary lists, the 8 themes, and all sources above.

Scoring / enrich / synth / dedup blocks copy SoftRobotic's values unchanged — haiku-4-5 scoring,
sonnet-4-5 enrich/synth, `min_score: 70`, local fastembed dedup at 0.85 / 30 days — except
`max_candidates: 250` and the new `rubric_prompt` content.

`sections:` keeps `material_requirements`, drops `job_openings`, adds `notable_products` and
`regulatory_watch`. All three `enabled: true`, sonnet-4-5, `max_searches: 6`. No `output_dir`.

### 3. Gate implementation — `sources/base.py`

Rewrite `vocabulary_match` (~10 lines today, single-axis) for the core-OR-(adjacent AND context)
rule, keeping the exclude-first short-circuit. Update the `User-Agent` in `fetch_url` to
`HSTIntelligence/0.1`. The rest of the file is domain-neutral.

### 4. Three weekly sections

`store/db.py` already has generic `_upsert_section(db, table, …)` / `_latest_section(db, table)`
helpers — **reuse them**. Keep the `material_requirements` wrapper pair and add two more; add two
tables to `store/schema.sql` of the same shape as the existing one (`week_start` PK, `week_end`,
`payload_json`, `generated_at`).

`pipeline/sections.py`: keep `_generate_section` and `_user_prompt` as-is; keep
`generate_material_requirements`, drop `generate_job_openings`, add `generate_notable_products` and
`generate_regulatory_watch` (usage keys `anthropic_notable_products`, `anthropic_regulatory_watch`).
**Preserve the failure isolation** — returning `None` when disabled, keyless, or on any exception is
what keeps one section's outage from breaking the weekly run.

`pipeline/run.py`: in the `weekly_synthesis` branch keep the materials call + upsert, add the two new
generators and theirs, drop the `write_jobs_doc` import and call, update the argparse description.

Prompts — all return strict JSON, all ground every row in a `web_search` result, none may invent URLs:

- **`prompts/material_requirements.md`** (rewrite) →
  `{"materials": [{application, material_class, key_properties, open_challenge, source_url}]}`, 6–9
  rows.
  - `application` — the tubing family or end use: thin-wall polyolefin wire marking, dual-wall
    adhesive-lined harness seal, PTFE/FEP catheter shaft liner, PVDF high-temp aerospace sleeve, PEEK
    downhole sleeve, EV busbar HV insulation.
  - `material_class` — base polymer + crosslinking route (irradiated polyolefin, e-beam vs. chemical,
    melt-processible fluoropolymer, elastomer).
  - `key_properties` — the numbers that matter: shrink ratio, continuous use temperature, dielectric
    strength, gel fraction, tensile/elongation retention after aging, chemical resistance.
  - `open_challenge` — the unsolved materials problem, explicitly including PFAS-free replacement
    paths where they apply.

  Push it toward numeric targets, not adjectives.
- **`prompts/notable_products.md`** → `{"products": [{product, manufacturer, material_construction,
  application, announced, source_url}]}`, 5–8 rows. Real launches only, no repackaged catalog pages.
- **`prompts/regulatory_watch.md`** → `{"regulations": [{regulation, body, change,
  status_effective_date, hst_impact, source_url}]}`, 5–8 rows. `hst_impact` must say what it changes
  for a tubing manufacturer.

### 5. Prompts for the feed path

- `prompts/relevance.md` — rewrite around the 8 HST themes. **One deliberate difference from
  SoftRobotic:** market/supplier news is *in scope* here (guide topic 7), so band it 55–75 rather
  than SoftRobotic's blanket <40 business-noise rule — while keeping pure finance (stock moves,
  earnings, analyst price targets) below 40 so technical work still outranks it.
- `prompts/enrich.md`, `prompts/synth.md` — same structure, HST audience: a TE Connectivity polymer
  engineer working on tubing formulation, crosslinking, and qualification.
- `pipeline/score.py` → `infer_theme()`: rewrite the keyword ladder for the 8 HST themes. Bootstrap
  fallback only, used when no API key is present.

### 6. Site — `site/build.py`

Structure and layout stay; the domain-coupled parts change:

- `SITE_CSS` `:root` — emerald → **amber** per the guide (`--signal:#b45309`,
  `--signal-soft:#fdf1e0`, `--signal-ink:#92400e`), navy retained. Also the two hardcoded emerald
  borders on `.prose a` and `table.matreq a`.
- `NAV` → `Feed / Archive / Weekly / Materials / Products / Regulatory`. (RSS was dropped from the
  nav and footer after launch; `feed.xml` is still built.) That many items is wide
  for the 62px sticky header — check the mobile breakpoint and shorten labels (`Reg.`) if it wraps.
- `CANONICAL_THEMES` + the `canonical_theme()` ladder → the 8 HST themes.
- Keep `render_materials`, retitled ("Materials" / "Each tubing family mapped to its base polymer,
  crosslinking route, property targets, and the open challenge"); add `render_products` and
  `render_regulatory` on the same table shell with new columns. Reuse `_source_link`, the
  `table.matreq` CSS, and the "not compiled yet" empty state for all three.
- `build_site()` — fetch all three sections, write `materials.html`, `products.html`,
  `regulatory.html`.
- Header/hero/`page_title` copy, and the `boost_terms()` config key (`materials_boost_terms` →
  `technical_boost_terms`).

### 7. Tests

The seven files in `tests/` embed the robotics vocabulary and section names:

- `test_sources.py`, `test_pipeline_run.py`, `test_model_integrations.py`, `test_dedup.py` — swap
  fixture vocab to HST terms; **add gate cases proving the two-axis rule**: core-only hit passes,
  adjacent-without-context fails, adjacent+context passes.
- `test_sections_and_pages.py` — drop the `jobs_doc` class entirely; cover all three sections
  (generator disabled / injected client / usage tracking, upsert+latest round-trip); assert each of
  `materials.html`, `products.html`, `regulatory.html` renders rows and the empty state.
- `test_store_and_site.py`, `test_synth.py` — update expected theme labels and page names.

### 8. Workflow + docs

- `.github/workflows/weekly.yml` — `cron: "0 15 * * 2"` (Tue 8 AM PDT), rename job and concurrency
  group, **delete** the Word-doc artifact-upload step. Keep test → run → build → commit db → Pages
  deploy. Drop the `VOYAGE_API_KEY` env line (dedup is local by default).
- `README.md` and `IMPLEMENTATION_STATUS.md` in SoftRobotic's format — what it produces, setup,
  commands, schedule, and a Pages launch checklist.
- `.env.example` — `ANTHROPIC_API_KEY` plus `HST_CONFIG` / `HST_DB` overrides.

---

## Verification

1. `make test` — all offline tests pass, no network, no API key.
2. **Offline end to end:** `make run` then `make build-site`. Without `ANTHROPIC_API_KEY` this
   exercises the keyword-bootstrap path and skips all three web-search sections. Confirm
   `data/tracker.db` is created, items land with `status='included'`, and
   `public/{index,archive,weekly,materials,products,regulatory}.html` + `feed.xml` + `index.json` all
   build. Open `public/index.html` and check the amber theme and the nav.
3. **Feed health:** run with `ANTHROPIC_API_KEY` set and read the per-feed errors logged into the
   `runs` table. Prune any `# verify` URL that 404/403s, then re-run. Watch the three `company_news`
   feeds specifically — confirm 3M / Zeus / Mattr each yield items (Mattr is the gzip suspect), since
   manufacturer newsrooms are the whole point of that group.
4. **Live run:** `python3 pipeline/run.py --config targeting.yaml --db data/tracker.db
   --weekly-synthesis`. Confirm scored items carry real themes and reasons, `weekly.html` has a
   synthesis, and all three section pages populate with real, clickable `source_url`s. On
   `materials.html` specifically, check the rows name actual tubing families and carry numeric
   property targets — a table of generic polymer adjectives means the prompt needs tightening.
5. **Precision spot-check** on the first scored set: are ≥80% of included items actually about heat
   shrink tubing or its materials/processes? If the gate over-admits generic polymer papers, tighten
   `context_terms`; if the week is thin, loosen. Tune `min_score` to land ~15–25 items/week.
6. **Deploy:** push, enable Pages from Actions, trigger `workflow_dispatch` with
   `weekly_synthesis: true`, confirm the deployed URL serves the site.

---

## Open items

- **The two-axis gate is the main thing to tune** after the first live run — see Verification 5. It
  is the one place this design departs from SoftRobotic, and the departure is a judgment call about
  HST's narrower vocabulary, not a proven setting.
- **Relevance banding for market news** (55–75) is likewise a first guess. If supplier/market items
  crowd out technical work in the feed ranking, lower the band rather than excluding the theme.
- **The old agent is retired.** Its weekly remote routine — "HST Intelligence Weekly Digest",
  `trig_01MsX5Pr334SSVspJBoW3UUS`, `0 16 * * 1`, repo `LeMa-3254/hst-intelligence` — was **disabled
  on 2026-07-24**, so the run scheduled for 2026-07-27 will not fire. It is disabled, not deleted:
  re-enable at https://claude.ai/code/routines/trig_01MsX5Pr334SSVspJBoW3UUS if this tracker stalls
  before it is producing. The code and past `.docx` output at `/Users/lele/Le_Documents/AI/hst_agent`
  and in `LeMa-3254/hst-intelligence` are untouched — that repo is the historical archive, and
  nothing here writes to it. **There is now a coverage gap** until the new tracker's first
  Tuesday run, which is worth accepting only if the build happens promptly.
