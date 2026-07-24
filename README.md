# HST Intelligence

HST Intelligence tracks fresh developments in **heat shrink tubing** — products, materials and
formulations, manufacturing and crosslinking, characterization, standards and regulatory action,
applications, market news, and academic R&D. It is a scheduled pipeline that ingests public sources,
filters + LLM-scores + enriches items, stores the archive in SQLite, and publishes a static GitHub
Pages site.

It shares the SoftRobotics Intelligence architecture; the domain content (topics, sources, search
queries) comes from the *Heat Shrink Tubing Intelligence Agent* setup guide. See [PLAN.md](PLAN.md)
for the build spec and the reasoning behind the domain adaptations.

## What it produces

A static site with:
- **Feed** — the week's ranked, scored developments, grouped by theme.

There is no RSS feed: the nav/footer links, `feed.xml`, and the `<link rel="alternate">` discovery
tag were all removed on request. `index.json` is still published for programmatic access to the
full archive.
- **Archive** — searchable/filterable full history.
- **Weekly** — a trend synthesis clustered by theme.
- **Materials** — each tubing family mapped to its base polymer, crosslinking route, numeric property
  targets, and the open challenge.
- **Products** — real heat shrink tubing launches: manufacturer, construction, application, date.
- **Regulatory** — UL / MIL / IEC / SAE / ISO / EPA / ECHA / FDA movement and what each changes for a
  tubing manufacturer.

The last three are generated weekly via LLM web search (the Anthropic server-side `web_search` tool),
not from RSS. Regulatory Watch is load-bearing rather than decorative: the standards bodies and
regulators publish no reliable feeds, so that section is the only path by which their activity reaches
the site.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Requires **Python 3.11+** (`models.py` uses `@dataclass(slots=True)`; `pipeline/model_clients.py` uses
the walrus operator in a comprehension). A system `python3` that is older will fail at import — use the
venv interpreter, not a global one.

Copy `.env.example` to `.env` and fill `ANTHROPIC_API_KEY` locally for live model calls. GitHub Actions
uses a repository secret instead of committing `.env`.

## Common Commands

```bash
make test
make run
make build-site
```

Equivalent direct commands:

```bash
python3 -m unittest discover -s tests
python3 pipeline/run.py --config targeting.yaml --db data/tracker.db
python3 pipeline/run.py --config targeting.yaml --db data/tracker.db --weekly-synthesis
python3 site/build.py --config targeting.yaml --db data/tracker.db --output public
```

The `--weekly-synthesis` run also generates the three web-search sections. Without an
`ANTHROPIC_API_KEY`, scoring/enrichment fall back to a keyword bootstrap and all three sections are
skipped — the pipeline still runs end to end and the site still builds, with the three section pages
showing their empty state.

## How targeting works

Everything domain-specific lives in [targeting.yaml](targeting.yaml) and [prompts/](prompts/). The one
structural difference from SoftRobotics Intelligence is the **keyword gate**, which is two-axis:

```
hst_core_terms  OR  (adjacent_terms  AND  context_terms)
```

A core anchor ("heat shrink", "shrink tubing", "cross-linked polyolefin") qualifies an item outright.
Otherwise it must pair polymer/process vocabulary (`adjacent_terms`: FEP, PVDF, extrusion, e-beam
crosslinking, PFAS…) with an HST context (`context_terms`: wire, cable, catheter shaft, busbar…). A
single-axis gate on "heat shrink" alone would surface two or three items a week and miss relevant work
that never uses the phrase; gating on the polymer vocabulary alone would drown the feed.

Tune precision vs. recall there, not in code. `scoring.min_score` should land ~15–25 items/week.

### Industry over academia

**This tracker's centre of gravity is industry, not journals.** Heat shrink tubing advances in
industry first — new tubing families, wall constructions, temperature ratings and PFAS-free
reformulations are announced by manufacturers, covered by trade press, and written into standards
long before they reach a paper. That weighting is expressed in four places, and they need to stay
consistent if you change one:

- `targeting.yaml` — `company_news` and `web_news` are **Tier A**; `arxiv`/`openalex`/`crossref` are
  **Tier B**.
- `prompts/relevance.md` — the rubric that governs a keyed run. General polymer research with no
  tubing/wire/cable application is banded **45–65 even when excellent**; launches and regulatory
  changes reach 85+.
- `pipeline/run.py` — `INDUSTRY_SOURCE_TYPES` sorts industry candidates first, so the
  `max_candidates` cap drops academic long-tail rather than product news. Mirrored in `site/build.py`
  for the home feed.
- `pipeline/score.py` — a `+10` industry prior in the offline bootstrap, so a keyless dry-run ranks
  the way a keyed run will.

One expectation to hold: **vendor RSS is a thin weekly signal.** Tubing manufacturers post a few
times a year, and conglomerate newsrooms (3M, Mattr) are investor-relations channels where heat
shrink never appears — both are disabled with reasons recorded. Actual launch coverage comes from the
launch-shaped `google_news` queries and the **Notable Products** web-search section.

The `company_news` feeds are an early-warning net, and carry **both** `max_age_days: 180` (so a
quarterly vendor post is ingested at all) and `feed_days: 180` (so it reaches the front page rather
than going straight to the Archive). Both are per-source overrides — academic and trade items stay on
the global 30-day windows.

`technical_boost_terms` deliberately excludes generic characterization vocabulary (DMA, DSC, TGA,
FTIR, SEM, tensile, bare `dielectric`). That vocabulary appears in every polymer paper, so it
correlates with "academic abstract", not with heat shrink tubing. What is listed correlates
specifically: named qualification standards, and the parameters unique to a shrinkable product.

## Cost

A scheduled weekly run costs roughly **$1.10** (~$58/year), measured on the 2026-07-24 live run at
list rates — haiku-4.5 $1/$5 per Mtok for scoring, sonnet-4.5 $3/$15 for everything else, and
web_search at $10 per 1,000 requests. Confirm against your own console; these are estimates.

| stage | input | output | searches | ~cost |
|---|---|---|---|---|
| scoring (haiku) | 28k | 2.3k | — | $0.04 |
| enrich + synth | 1.8k | 0.6k | — | $0.01 |
| material_requirements | 44k | 2.9k | 6 | $0.24 |
| **notable_products** | **155k** | 2.0k | **12** | **$0.62** |
| regulatory_watch | 38k | 2.2k | 6 | $0.21 |

**`notable_products` is 55% of the bill**, and the reason is worth understanding before you tune it:
the per-search fee is the *small* part. Each web search feeds its results back as input tokens, so
raising `max_searches` 6 → 12 took that section from 63k to 155k input — $0.27 in result tokens
against $0.12 in search fees. It earns its keep (at 6 searches it returned an empty table, at 12 it
returns 7 real launches), but if you want the run cheaper, that dial is where the money is.

The `runs` table records `web_search_requests` alongside token counts, so per-run spend is auditable:

```sql
SELECT started_at, token_usage_json FROM runs ORDER BY id DESC LIMIT 1;
```

Ad-hoc reruns while tuning cost the same as scheduled ones — regenerating a single section twice
during development roughly doubled a week's spend.

## Schedule

The GitHub Actions workflow runs weekly on **Tuesdays at 8:00 AM PDT** (`cron: 0 15 * * 2`) with
synthesis, builds the static site, deploys to GitHub Pages, and commits `data/tracker.db` back when it
changes. GitHub cron is UTC-only, so the run lands at 7:00 AM PST during standard time.

## GitHub Pages Launch Notes

After the repository exists on GitHub (`LeMa-3254/HST-development-tracker`):

1. Add repository secret `ANTHROPIC_API_KEY` (the only key required). `VOYAGE_API_KEY` is optional —
   add it only if you switch `dedup.embedding_provider` to `voyage`; by default dedup uses local
   fastembed embeddings.
2. Enable Pages from GitHub Actions in repository settings; the repo must be public on the free plan.
3. Confirm Pages serves the project URL: `https://lema-3254.github.io/HST-development-tracker/`.
4. Update `targeting.yaml` (`site.url`) if a custom domain replaces the Pages URL.
5. Verify the `# verify` feed URLs in `targeting.yaml` after the first run and prune any that 404/403
   (the adapters log per-feed failures into the `runs` table without breaking the run). Watch the three
   `company_news` feeds in particular — manufacturer newsrooms are the earliest signal for product
   launches, so a silent failure there costs the most.

## Relationship to the previous agent

The earlier `hst_agent` (a single `agent.py` emitting a weekly Word doc to `LeMa-3254/hst-intelligence`)
is **retired** — its cloud routine was disabled on 2026-07-24. That repo remains as the historical
archive of past `.docx` digests; nothing here writes to it. See PLAN.md "Open items" for how to
re-enable it if needed.
