# HST Intelligence — Implementation Status

## Current Status

Built from the SoftRobotics Intelligence pipeline and re-targeted to heat shrink tubing, per
[PLAN.md](PLAN.md) Steps 1–8, then retargeted industry-first (see that section below). The scaffold
is complete and **verified live** — 68 tests pass, and a keyed
`python3 pipeline/run.py --weekly-synthesis` + `make build-site` produces the database, a real weekly
synthesis, and all seven site pages with all three web-search sections populated. See "First live
run" below. What remains is pushing to GitHub and the first Actions run.

Built and verified 2026-07-24.

## Completed

**Step 1 — scaffold.** Copied the SoftRobotics architecture (`pipeline/ sources/ store/ site/
prompts/ tests/ .github/workflows/` plus `config.py`, `models.py`, `Makefile`, `pyproject.toml`,
`requirements.txt`, `.env.example`, `.gitignore`) and stripped instance state (git, venv, db, caches,
`.env`, `output/`). Dropped `pipeline/jobs_doc.py`, `prompts/jobs.md`, `python-docx`, and the
`output/` gitignore entry — this tracker is site-only.

**Step 2 — `targeting.yaml`.** Full rewrite: HST site identity, the three-list two-axis vocabulary,
`technical_boost_terms` (named standards + shrinkable-product parameters), conservative excludes, the guide's 8 topic
areas as the fixed theme taxonomy, and all sources. `scoring.max_candidates` raised 200 → **250** to
absorb the widened company/regulator query set. Every dead feed is recorded in `disabled_feeds` with
its probe reason so it is not rediscovered later.

**Step 3 — the gate.** `sources/base.py vocabulary_match` rewritten from single-axis to
`core OR (adjacent AND context)`, keeping the exclude-first short-circuit. `fetch_url` User-Agent →
`HSTIntelligence/0.1`. Added `decompress_if_gzip` (gzip-magic-byte sniff) — `mattr.com/feed/` serves
gzip with no `Accept-Encoding` request header, which urllib does not unwrap, so that feed would
otherwise die at the XML parser. Added `CompanyNewsAdapter` + the `company_news` key in
`pipeline/ingest.py`.

**Step 4 — three weekly sections.** Two new tables in `store/schema.sql` alongside
`material_requirements`, and two new wrapper pairs on the existing generic `_upsert_section` /
`_latest_section` helpers (no new storage machinery). `pipeline/sections.py` gained
`generate_notable_products` / `generate_regulatory_watch` on the shared `_generate_section`, with the
failure isolation preserved — returning `None` on disabled / keyless / any exception. `pipeline/run.py`
calls all three in the `--weekly-synthesis` branch. `prompts/material_requirements.md` rewritten for
tubing families; `prompts/notable_products.md` and `prompts/regulatory_watch.md` written new.

**Step 5 — feed-path prompts.** `relevance.md` rewritten around the 8 HST themes, with market/supply
news **banded 55–75** (in scope per the guide) while pure finance stays <40. (The rubric was
reworked again in the industry-retargeting pass below — that section is the current description.) `enrich.md` and `synth.md` re-aimed at a polymer engineer working on tubing formulation,
crosslinking, and qualification. `pipeline/score.py infer_theme` ladder rewritten for the 8 themes,
with academic source types as a final fallback (bootstrap path only).

**Step 6 — site.** Emerald → **amber** (`--signal:#b45309`), with the two hardcoded emerald link
borders lifted into a `--signal-line` variable rather than re-hardcoded. Nav expanded to 7 items;
because seven does not fit a 62px header on a phone, the mobile breakpoint makes the nav scroll
horizontally rather than wrap to two rows (wrapping would break the sticky offset the `.tabs` bar
depends on). `CANONICAL_THEMES` + `canonical_theme()` → the 8 HST themes. The three section pages
share one `render_section_page` renderer differing only in columns, so they reuse the existing
`table.matreq` shell, `_source_link`, and empty state.

**Step 7 — tests.** All fixtures re-vocabularied. Added a `GateTests` class pinning each branch of
the two-axis rule (core-only passes; adjacent-without-context fails; context-without-adjacent fails;
adjacent+context passes; split across title/abstract passes; excludes hard-drop even with a core
term), gzip round-trip tests, a `company_news` adapter test, per-section usage-key and
failure-isolation tests, upsert/latest round-trips for all three tables, and render + empty-state
assertions for all three pages. Dropped the `jobs_doc` test class. (Now **68 tests** after the
industry-retargeting and live-run work below added ordering, freshness, feed-window, and
synthesis-window cases.)

**Step 8 — workflow + docs.** `weekly.yml` → `cron: "0 15 * * 2"` (Tue 8:00 AM PDT), renamed job and
concurrency group, artifact-upload step deleted, `VOYAGE_API_KEY` env line dropped. `README.md`,
this file, and `.env.example` (`HST_CONFIG` / `HST_DB`) written.

## Verified (offline, 2026-07-24)

- **`make test`** — 68 tests pass, no network, no API key.
- **`make run`** (no `ANTHROPIC_API_KEY`) — exercises the keyword-bootstrap path. Final counts from
  the `runs` table: `fetched 86 → candidates 13 → scored 13 → included 5`, **zero feed errors**.
  (The first run, before the industry retargeting below, was `74 → 11 → 11 → 3` with all 3 included
  items from Crossref.) Every feed URL probed fetched and parsed cleanly from a home IP; nothing in
  the enabled set 404s or 403s locally.
- **`make build-site`** — writes `index/archive/weekly/materials/products/regulatory.html` +
  `feed.xml` + `index.json`. Confirmed in the built HTML: amber `--signal:#b45309` present and no
  emerald left anywhere; the 7-item nav renders `Feed / Archive / Weekly / Materials / Products /
  Regulatory / RSS`; all three section pages render their empty state (correct — the web-search
  sections are skipped without a key).
- Feed liveness spot-checks: every `company_news` feed returns items. The gzip fallback was verified
  against Mattr (since disabled for irrelevance, but kept as the recorded gzip case).
- `python3` on this machine is Anaconda 3.7 and cannot run the project; use `.venv/bin/python`
  (3.14) or `make test PYTHON=.venv/bin/python`.

### Config changes made during verification

- **OpenAlex returned literally zero.** The original two-clause `A AND B` search is parsed by OpenAlex
  into a strict AND-of-ORs over full text; with a 7-day window on a niche topic that matched nothing.
  Simplified to a single clause — the local two-axis gate does the second-axis job downstream anyway,
  so the extra narrowing only cost recall.
- **npj Computational Materials serves an empty feed** (HTTP 200, zero `<item>` elements). Moved to
  `disabled_feeds` with the reason recorded. It was the least HST-relevant of the journal set —
  carried over from SoftRobotics Intelligence rather than chosen for this domain.
- **`journal_rss` disabled** (decision taken 2026-07-24). The four feeds are live and generous —
  Polymer 99, J. Applied Polymer Science 86, Polymer Engineering & Science 108, Advanced Materials
  329, so **622 raw items** — and **all 622 failed the gate**: `core_hit 0, adjacent_hit 28,
  context_hit 14, both 0`.

  The cause is the shape of the data, not the targeting. ScienceDirect and Wiley put *bibliographic
  metadata* in the RSS `description`, not the abstract — a typical one reads "Publication date: 13
  October 2026 Source: Polymer, Volume 363 Author(s): …". So the gate judged on the **title alone**,
  and a polymer-journal title almost never carries both a polymer term and a wire/cable context word.

  Crossref and OpenAlex index the same journals and do carry real abstracts — Crossref supplied every
  included item on the verification run — so disabling the group loses no coverage, only four wasted
  HTTP fetches a week. Same call, and same stated reason, as the ACS feeds. Each feed is preserved in
  `disabled_feeds` with its measured item count, so the decision is auditable and reversible.

  It only becomes worth re-enabling if the gate is relaxed for Tier A academic sources (venue as the
  quality filter, `core OR adjacent`), which would admit ~28 items/week — a sample of which are
  genuinely off-topic ("Fluorinated Polyimide Aerogel"), so that trades precision and tokens for
  recall.

## Industry-weighted retargeting (2026-07-24)

The first verification run surfaced all 3 included items from Crossref and **zero** from company or
trade sources — backwards for a domain where progress comes from industry, not journals. Four
separate mechanisms were biasing academic, and all four were changed:

1. **Source tiering inverted.** `company_news` and `web_news` promoted to **Tier A**;
   `arxiv`/`openalex`/`crossref` demoted to **Tier B**. Tier drives `TIER_POINTS` in bootstrap
   scoring.
2. **`prompts/relevance.md` reweighted** — the lever that governs a keyed run. States the tracker's
   centre of gravity is industry, reorders the three valuable item types to put launches and
   regulatory first, adds a **45–65 band for general polymer research with no tubing/wire/cable
   application** ("do not score these in the 80s just because they are rigorous — rigour is
   `quality`, not `relevance`"), and adds six worked examples. `prompts/synth.md` reordered to match.
3. **Candidate prefilter ranks industry first** (`pipeline/run.py INDUSTRY_SOURCE_TYPES`), so the
   `max_candidates` cap drops academic long-tail rather than product news. Previously it sorted on
   `technical_boost_terms` — DSC, TGA, dielectric, tensile — which is the vocabulary papers are
   written in, so it was an academic-first sort wearing a technical label. Same change to the home
   feed ranking in `site/build.py`.
4. **Bootstrap scoring gained an industry prior** (`+10` for curated industry source types) so an
   offline dry-run ranks the way a keyed run will. Deliberately **excludes `google_news`** — it is an
   industry source but an unvetted firehose whose market-forecast listicles would ride the bonus past
   `min_score`; there is a test pinning that.

### Two structural findings behind the change

- **Manufacturer RSS is a thin weekly signal in this industry.** Tubing vendors post a handful of
  times a *year*, and conglomerate newsrooms are investor-relations channels. 3M returned **0 of 5**
  gated items (Q2 earnings, a Microsoft AI partnership, Scotch Kids Tape) and Mattr **0 of 10** (ESG
  reports, CEO interviews) — both disabled with reasons. Replaced with vendor feeds that carry real
  tubing content: **DSG-Canusa** (8/10 gated — the best hit rate found), **Putnam Plastics** (4/10,
  including "Expands Portfolio to Include FEP Heat Shrink"), keeping **Zeus** (2/10, on-topic but
  quarterly). Qualtek (dormant since 2023) and Gremtek (French-language, English-only vocabulary)
  recorded as disabled.

  Consequence to hold onto: **launch coverage really comes from the launch-shaped `google_news`
  queries and the Notable Products web-search section**, not from vendor RSS. The company feeds are a
  cheap early-warning net, not the primary channel.

- **The 30-day freshness ceiling was silently deleting the entire group.** Every gated
  `company_news` item was months old, so `is_fresh` dropped all of them. Added **per-source
  `max_age_days`** (`pipeline/run.py max_age_days_for`), with `company_news: 180`, plus a matching
  per-source **`feed_days`** override (`site/build.py feed_days_for`) so those posts reach the front
  page rather than being ingested straight into the Archive. Academic and trade items are still held
  to the global 30-day home-feed window.

Also added two on-domain trade titles found while probing: **Wiring Harness News** and **Connector
Supplier**.

### Two follow-on corrections

- **`technical_boost_terms` rescoped.** The guide's characterization vocabulary (DMA, DSC, TGA,
  FTIR, SEM/EDX, tensile, Instron, and bare `dielectric`) was removed. It appears in essentially
  every polymer paper ever written, so it correlated with "this is an academic abstract" rather than
  with heat shrink tubing — handing journal items a standing +15 that carried no relevance signal.
  What remains correlates specifically with HST: the named standards a tubing product is qualified to
  (UL 224, MIL-I-23053, IEC 60684, SAE AS23053, ISO 6722, ASTM D2671, RoHS, REACH) and the parameters
  unique to a shrinkable product (shrink/expansion ratio, recovery and continuous-use temperature,
  recovered wall thickness, gel fraction, irradiation dose, dual-wall, adhesive liner, PFAS-free).

  Immediate effect: "Low-dielectric-loss poly(ester imide)s with chain-end crosslinking" fell 83 → 68
  and out of the feed. It was riding the bare `dielectric` boost despite having no tubing connection.

- **Vendor posts promoted to the front page.** Per-source **`feed_days`** (`site/build.py
  feed_days_for`), with `company_news: 180`, mirroring the `max_age_days` override. Without it the
  ingestion window admitted vendor posts but `site.feed_days: 30` held them out of the home feed, so
  they went straight to the Archive. Academic and trade items are still held to the global 30-day
  window — the override is per-source, not a blanket loosening.

**Result:** `fetched 86 → candidates 13 → included 5`, zero feed errors, and the top three ranked
items are industry (`web_news`, `company_news`, `company_news`) ahead of the Crossref papers, with
the Zeus posts on the front page. **68 tests pass.**

## First live run (with `ANTHROPIC_API_KEY`, 2026-07-24)

`python3 pipeline/run.py --weekly-synthesis` + `make build-site`. Exit 0, **zero feed errors**.

- Counts: `fetched 88 → candidates 13 → scored 13 → included 2`.
- Cost: **~268k input / ~10k output tokens + 24 web searches** ≈ **$1.11 per weekly run** (~$58/yr).
  See the cost table in README.md. `notable_products` is 55% of it.
- All three sections populated: **Materials 9 rows, Notable Products 7, Regulatory Watch 7.**
- Weekly synthesis renders with real linked content.

**The rubric works as designed.** Academic papers scored high *quality* and low *relevance* —
`r62/q78`, `r52/q68` — which is the "rigour is `quality`, not `relevance`" instruction doing exactly
its job. Industry items led (`r78` Zeus PFX Flex, `r72` e-beam crosslinking for wire & cable), and the
Google News market-forecast listicles landed at `r22`/`r18`. Themes were assigned sensibly
(Products & Launches, Manufacturing & Processing, Academic R&D).

**Materials output is genuinely good** — 8–9 rows carrying real numbers (2:1 shrink ratio, 60–80% gel
fraction target, ≥39 kV/mm, −55 to +175 °C, MIL-DTL-23053/5C, AMS-DTL-23053/4 Class 3) rather than
adjectives, which was PLAN.md Verification 4's specific concern. **Regulatory output is strong** —
UL 224 Ed. 8, IEC 60684-2:2025, IEC 60684-3-281:2025, SAE AS23053C, the EPA TSCA 8(a)(7) reporting
delay, and the ECHA universal PFAS restriction, each with a real date and a concrete manufacturer
impact.

### Three fixes the live run forced

- **Notable Products returned an empty table.** The prompt demanded launches from the last 30 days,
  never past 90 — in an industry that announces a few times a year that finds nothing. Widened to
  12 months, broadened to include product-line expansions / reformulations / new qualifications
  (still requiring a date), and added explicit search-angle guidance. Also raised its `max_searches`
  6 → **12**: vendor launches are poorly indexed, and 6 searches returned 0 rows, then 1. At 12 it
  returns 7 real launches (Nordson MEDICAL PolyPeel, Junkosha clear peelable, Cobalt 74D Pebax,
  Pexco HS-101, TE VOLINSU EV busbar on an earlier pass). This section is the expensive one —
  ~139k input tokens — and is worth it.

- **The weekly synthesis rendered "No included items for this week yet."** `last_complete_week_bounds`
  is a strict Mon–Sun window; the two included items were dated 2026-07-06 and 2026-03-04, either
  side of 2026-07-13..19. In a domain this sparse that page would be empty most weeks. Added
  `synth.lookback_days` (`pipeline/synth.py synthesis_bounds`), set to **30**, which widens the start
  while keeping the week end. The returned start is also the `weekly_summaries` primary key, so it
  still advances once per run and the label on the page matches what was actually summarized.

- **The API key was placed in `.env.example`**, the committed template, rather than `.env`, which is
  gitignored. Moved to `.env` (mode 600) and the template restored to a placeholder with a warning
  comment. Nothing was committed — the project is not a git repo yet — so there was no exposure, but
  it would have shipped with the first push to a public repo.

### Cost accounting, and a tracking gap it exposed

The whole session billed **$2.71**, not the ~$1 a single run costs, and reconciling that turned up a
real defect. Two causes:

- **Four section-generating passes, not one** — the first full run, two `notable_products`
  regenerations while fixing the empty table, then a second full run after the database was deleted.
  654k input / 20k output tokens and ~60 searches in total. The `runs` table showed only the last
  pass because the db had been wiped, which is what made the first estimate look low.
- **`anthropic_usage` never recorded web-search requests.** They live in
  `usage.server_tool_use.web_search_requests`, a nested object the four token keys miss, so the
  `runs` table — the thing you would use to monitor spend — was blind to the per-request charge on
  exactly the three most expensive stages. **Fixed**, with two tests; a live call now records
  `web_search_requests: 6`.

The larger lesson is that the per-search fee is the minor term. Each search feeds its results back
as input tokens, so `notable_products` going 6 → 12 searches cost **$0.27 in result tokens against
$0.12 in fees**. That dial is where the money is if the run needs to be cheaper.

### Known limitation: the feed is thin

**2 included items** against PLAN.md's 15–25/week target. The constraint is candidate supply, not the
threshold: 88 fetched → only 13 pass the gate, and lowering `min_score` from 70 to 55 would yield 4
rather than 25. Heat shrink tubing simply does not generate 20 RSS-visible developments a week.

The three web-search sections are where the weekly value actually is — **23 rows of substantive,
sourced content** against 2 feed items. Worth deciding whether to lower `min_score` to ~55 to give
the feed page more body, accepting weaker items, or to leave it strict and treat the feed as a
supplement to the section pages.

## Remaining

- **Create and push the repo** `LeMa-3254/HST-development-tracker` (public), add the
  `ANTHROPIC_API_KEY` secret, enable Pages from Actions, and confirm the deployed URL serves the site.
  Confirm `.env` is absent from the first commit (it is gitignored; `.env.example` is the template).
- **Decide `min_score`** — see "Known limitation: the feed is thin" above.
- **First live run** (PLAN.md Verification 3–4): read the per-feed errors in the `runs` table and
  prune any `# verify` URL that 404/403s. All feeds passed cleanly from a home IP, but CI runners are
  blocked differently — the first Actions run's error log is the real verdict.
- **Tune the gate** (PLAN.md Verification 5). The two-axis rule is a judgment call about HST's narrow
  vocabulary, not a proven setting. Check that ≥80% of included items are really about heat shrink
  tubing or its materials/processes; tighten `context_terms` if generic polymer papers get in, loosen
  if the week is thin. Also watch `candidates` vs. `scored` in the `runs` table — if candidates
  routinely hit the 250 cap, tighten the Google News queries before raising it.
- **Check the market-news band** (55–75). If supplier/market items crowd out technical work in the
  feed ranking, lower the band rather than excluding the theme.
- **Check `materials.html` rows carry numeric property targets.** A table of generic polymer
  adjectives means `prompts/material_requirements.md` needs tightening.
