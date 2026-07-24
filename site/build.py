from __future__ import annotations

import argparse
from datetime import date
from html import escape
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_config
from store.db import (
    connect,
    included_items,
    latest_material_requirements,
    latest_notable_products,
    latest_regulatory_watch,
    latest_weekly_summary,
    weekly_summaries,
)


# ---------------------------------------------------------------------------
# Identity: "heat shrink tubing radar / lab-instrument readout".
# Cool paper + navy ink + one amber signal accent (the guide's palette).
# Space Grotesk / Inter / IBM Plex Mono.
# Signature: the bracket [ … ] motif, and a 5-bar relevance signal meter.
# ---------------------------------------------------------------------------
FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=IBM+Plex+Mono:wght@400;500;600&"
    "family=Inter:wght@400;450;500;600;700&"
    'family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">'
)

SITE_CSS = """
:root{
  --paper:#f4f5f7;--surface:#ffffff;--ink:#14171f;--ink-soft:#434a59;--muted:#717885;
  --faint:#9aa0ac;--line:#e7e9ef;--line-strong:#d7dae2;--navy:#1a2440;
  --signal:#b45309;--signal-soft:#fdf1e0;--signal-ink:#92400e;--signal-line:#f0d4ab;
  --sans:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --display:"Space Grotesk",var(--sans);--mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --maxw:920px;--radius:16px;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;font-family:var(--sans);color:var(--ink);background:var(--paper);
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased;font-feature-settings:"cv05","ss01"}
a{color:inherit;text-decoration:none}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 22px}
.mono{font-family:var(--mono)}

/* header */
.site-header{position:sticky;top:0;z-index:30;background:rgba(244,245,247,.82);
  backdrop-filter:saturate(180%) blur(12px);-webkit-backdrop-filter:saturate(180%) blur(12px);
  border-bottom:1px solid var(--line)}
.header-inner{display:flex;align-items:center;justify-content:space-between;height:62px;gap:18px}
.brand{display:flex;align-items:baseline;gap:2px;font-family:var(--display);font-weight:700;
  font-size:1.24rem;letter-spacing:-.02em;color:var(--ink)}
.brand .br{font-family:var(--mono);font-weight:600;color:var(--signal)}
.brand sub{font-family:var(--mono);font-size:.62em;color:var(--signal);font-weight:600}
.nav{display:flex;gap:2px;align-items:center}
.nav a{padding:8px 13px;border-radius:9px;font-size:.86rem;font-weight:500;color:var(--muted)}
.nav a:hover{color:var(--ink);background:#eceef2}
.nav a.active{color:var(--ink);background:#e6e8ef}

/* eyebrow / labels */
.eyebrow{font-family:var(--mono);font-size:.72rem;font-weight:500;letter-spacing:.16em;
  text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:8px}
.eyebrow .br{color:var(--signal)}

/* hero */
.hero{padding:44px 0 14px}
.hero h1{font-family:var(--display);font-weight:600;font-size:2.5rem;line-height:1.06;
  letter-spacing:-.03em;margin:16px 0 0;max-width:18ch}
.hero h1 em{font-style:normal;color:var(--signal)}
.hero .lede{margin:14px 0 0;color:var(--ink-soft);font-size:1.05rem;max-width:54ch}
.statline{display:flex;flex-wrap:wrap;gap:0;margin:26px 0 0;border:1px solid var(--line);
  border-radius:12px;background:var(--surface);overflow:hidden}
.stat{padding:13px 18px;border-right:1px solid var(--line);min-width:120px}
.stat:last-child{border-right:0}
.stat b{font-family:var(--display);font-size:1.35rem;font-weight:600;display:block;letter-spacing:-.02em}
.stat span{font-family:var(--mono);font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}

/* category tabs */
.tabs{display:flex;flex-wrap:wrap;gap:7px;padding:26px 0 4px;position:sticky;top:62px;z-index:10;
  background:linear-gradient(var(--paper) 72%,transparent)}
.tab{font:inherit;font-size:.84rem;font-weight:500;cursor:pointer;color:var(--ink-soft);
  background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:7px 13px;
  display:inline-flex;align-items:center;gap:7px;transition:border-color .12s,color .12s,background .12s}
.tab:hover{border-color:var(--line-strong)}
.tab .tab-n{font-family:var(--mono);font-size:.7rem;color:var(--faint)}
.tab.is-active{background:var(--navy);border-color:var(--navy);color:#fff}
.tab.is-active .tab-n{color:#aab2c8}

/* feed + cards */
.feed{padding:14px 0 48px}
.section-label{font-family:var(--mono);font-size:.74rem;font-weight:500;letter-spacing:.12em;
  text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:10px;margin:24px 0 12px}
.section-label .br{color:var(--signal);font-weight:600}
.section-label::after{content:"";flex:1;height:1px;background:var(--line)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:20px 22px;margin:11px 0;transition:border-color .14s ease,box-shadow .14s ease,transform .14s ease}
.card:hover{border-color:var(--line-strong);box-shadow:0 10px 30px -16px rgba(20,30,60,.28);transform:translateY(-1px)}
.card-top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:11px}
.chip{font-family:var(--mono);font-size:.7rem;font-weight:500;letter-spacing:.04em;color:var(--navy);
  background:#eef0f6;border-radius:7px;padding:4px 9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60%}
.card-title{font-size:1.07rem;font-weight:600;line-height:1.34;letter-spacing:-.012em;margin:0;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.card-title a:hover{color:var(--signal-ink)}
.card-meta{font-family:var(--mono);font-size:.74rem;color:var(--muted);margin:9px 0 0;
  display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.card-meta .src{color:var(--ink-soft);font-weight:500}
.card-meta .sep{color:var(--line-strong)}
.summary{margin:11px 0 0;color:var(--ink-soft);font-size:.95rem;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.why{margin:13px 0 0;padding:10px 14px;background:#fbfbfc;border:1px solid var(--line);
  border-left:3px solid var(--signal);border-radius:0 10px 10px 0;font-size:.875rem;color:var(--ink-soft)}
.why b{font-family:var(--mono);font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;
  color:var(--signal-ink);font-weight:600;display:block;margin-bottom:3px}

/* relevance signal meter (0–100 score) */
.signal{display:inline-flex;align-items:flex-end;gap:3px;height:15px;flex:none}
.signal i{width:4px;border-radius:1.5px;background:var(--line-strong);display:block}
.signal i:nth-child(1){height:6px}.signal i:nth-child(2){height:8.5px}.signal i:nth-child(3){height:11px}
.signal i:nth-child(4){height:13px}.signal i:nth-child(5){height:15px}
.signal i.on{background:#b9c0d0}
.signal .signal-num{font-family:var(--mono);font-size:.76rem;font-weight:600;color:var(--muted);
  margin-left:6px;align-self:center}
.signal-high i.on{background:var(--signal)}
.signal-high .signal-num{color:var(--signal-ink);font-weight:700}
.hi-badge{font-family:var(--mono);font-size:.62rem;font-weight:600;letter-spacing:.12em;
  text-transform:uppercase;color:var(--signal-ink);background:var(--signal-soft);
  border-radius:6px;padding:3px 7px;margin-left:8px}

/* empty */
.empty{padding:44px 0;text-align:center;color:var(--faint);font-family:var(--mono);font-size:.85rem}

/* page head (archive/weekly) */
.page-head{padding:40px 0 2px}
.page-head h1{font-family:var(--display);font-weight:600;font-size:1.85rem;letter-spacing:-.025em;margin:12px 0 0}
.page-head p{margin:9px 0 0;color:var(--ink-soft)}

/* toolbar */
.toolbar{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin:22px 0 4px}
.toolbar label{display:grid;gap:7px;font-family:var(--mono);font-size:.68rem;font-weight:500;
  letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.toolbar input,.toolbar select{appearance:none;-webkit-appearance:none;font:inherit;font-size:.92rem;
  color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:11px;
  padding:11px 13px;min-height:44px;min-width:0;width:100%}
.toolbar input:focus,.toolbar select:focus{outline:none;border-color:var(--signal);box-shadow:0 0 0 3px var(--signal-soft)}
.result-count{font-family:var(--mono);font-size:.74rem;letter-spacing:.06em;color:var(--muted);margin:18px 0 0}

/* weekly prose */
.prose h2{font-family:var(--display);font-size:1.2rem;font-weight:600;letter-spacing:-.01em;margin:22px 0 8px}
.prose h2:first-child{margin-top:0}
.prose h3{font-family:var(--mono);font-size:.78rem;font-weight:500;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);margin:18px 0 6px}
.prose p{margin:8px 0;color:var(--ink-soft);font-size:.96rem}
.prose ul{margin:8px 0;padding-left:0;list-style:none}
.prose li{margin:9px 0;padding-left:20px;position:relative;color:var(--ink-soft);font-size:.96rem;line-height:1.5}
.prose li::before{content:"]";font-family:var(--mono);color:var(--signal);position:absolute;left:2px;font-size:.85rem}
.prose a{color:var(--signal-ink);font-weight:500;border-bottom:1px solid var(--signal-line)}
.prose a:hover{border-bottom-color:var(--signal)}
.prose-clip{max-height:208px;overflow:hidden;position:relative;
  -webkit-mask-image:linear-gradient(#000 60%,transparent);mask-image:linear-gradient(#000 60%,transparent)}
.weekly-meta{font-family:var(--mono);font-size:.72rem;letter-spacing:.06em;color:var(--faint);margin:0 0 8px}
.weekly-link{display:inline-block;margin-top:12px;font-family:var(--mono);font-size:.78rem;
  letter-spacing:.04em;color:var(--signal-ink);font-weight:500}

/* footer */
.site-footer{border-top:1px solid var(--line);margin-top:34px;background:var(--surface)}
.footer-inner{display:flex;flex-wrap:wrap;gap:14px;justify-content:space-between;align-items:center;
  padding:24px 22px;color:var(--faint);font-family:var(--mono);font-size:.74rem;letter-spacing:.04em;
  max-width:var(--maxw);margin:0 auto}
.footer-inner a{color:var(--muted)}
.footer-inner a:hover{color:var(--signal-ink)}

/* material requirements table */
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);margin:14px 0}
table.matreq{border-collapse:collapse;width:100%;min-width:720px;font-size:.9rem}
table.matreq th{font-family:var(--mono);font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);text-align:left;padding:12px 16px;border-bottom:1px solid var(--line-strong);white-space:nowrap}
table.matreq td{padding:13px 16px;border-bottom:1px solid var(--line);color:var(--ink-soft);vertical-align:top}
table.matreq tr:last-child td{border-bottom:0}
table.matreq td.app{color:var(--ink);font-weight:600}
table.matreq td.chal{color:var(--signal-ink)}
table.matreq a{color:var(--signal-ink);border-bottom:1px solid var(--signal-line)}
.section-note{font-family:var(--mono);font-size:.72rem;letter-spacing:.04em;color:var(--faint);margin:6px 0 0}

a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{
  outline:2px solid var(--signal);outline-offset:2px;border-radius:6px}
@media (max-width:680px){
  .toolbar{grid-template-columns:1fr}
  .hero h1{font-size:1.95rem}
  .stat{flex:1 1 40%}
  /* Six nav items do not fit a 62px header on a phone. Rather than wrap the header to two
     rows (which would break the sticky offset the .tabs bar depends on), let the nav scroll
     horizontally and tighten the labels. */
  .header-inner{gap:10px}
  .brand{font-size:1.02rem;flex:none}
  .nav{flex:1;justify-content:flex-end;overflow-x:auto;-webkit-overflow-scrolling:touch;
    scrollbar-width:none;-ms-overflow-style:none;mask-image:linear-gradient(90deg,transparent 0,#000 14px)}
  .nav::-webkit-scrollbar{display:none}
  .nav a{padding:8px 9px;font-size:.8rem;white-space:nowrap}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

NAV = [
    ("index.html", "Feed"),
    ("archive.html", "Archive"),
    ("weekly.html", "Weekly"),
    ("materials.html", "Materials"),
    ("products.html", "Products"),
    ("regulatory.html", "Regulatory"),
]

CANONICAL_THEMES = [
    "Products & Launches",
    "Materials & Formulations",
    "Manufacturing & Processing",
    "Characterization & Testing",
    "Standards & Regulatory",
    "Applications",
    "Market & Supply Chain",
    "Academic R&D",
]

# Home feed: ranked (relevance, then quality), technical items first, capped.
INDEX_LIMIT = 48


def build_site(config_path: str = "targeting.yaml", db_path: str = "data/tracker.db", output_dir: str = "public") -> None:
    config = load_config(config_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as db:
        items = included_items(db)
        latest_weekly = latest_weekly_summary(db)
        all_weeklies = weekly_summaries(db)
        materials = latest_material_requirements(db)
        products = latest_notable_products(db)
        regulations = latest_regulatory_watch(db)

    # The home feed and RSS are a *current* feed: show only recent items so old archive
    # entries don't dominate the relevance ranking. The Archive and JSON export keep everything.
    recent = [item for item in items if within_days(item, feed_days_for(item, config))]

    (output / "index.html").write_text(render_index(config, recent, latest_weekly), encoding="utf-8")
    (output / "archive.html").write_text(render_archive(config, items), encoding="utf-8")
    (output / "weekly.html").write_text(render_weekly(config, all_weeklies), encoding="utf-8")
    (output / "materials.html").write_text(render_materials(config, materials), encoding="utf-8")
    (output / "products.html").write_text(render_products(config, products), encoding="utf-8")
    (output / "regulatory.html").write_text(render_regulatory(config, regulations), encoding="utf-8")
    (output / "index.json").write_text(
        json.dumps([dict(item) for item in items], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    # No RSS. The feed, its nav/footer links, and the <link rel="alternate"> discovery tag were
    # all removed on request — the alternate tag is what makes browsers and reader extensions
    # show an RSS affordance even with no visible link on the page. index.json remains for
    # anyone wanting the archive programmatically.


def feed_days_for(item, config: dict) -> int:
    """Per-source home-feed window, falling back to site.feed_days.

    Mirrors pipeline/run.py's max_age_days_for. Manufacturer newsrooms post a few times a year,
    so under the global 30-day window a vendor's only heat shrink post of the quarter would be
    ingested and archived but never reach the front page — which is where a tubing engineer
    actually wants it."""
    source = config.get("sources", {}).get(field(item, "source_type"))
    if isinstance(source, dict) and source.get("feed_days") is not None:
        return int(source["feed_days"])
    return int(config.get("site", {}).get("feed_days", 0) or 0)


def within_days(item, days: int) -> bool:
    """True if the item's effective date (published, else fetched) is within `days` of today.
    days <= 0 disables the window. Undated items are treated as current."""
    if days <= 0:
        return True
    value = field(item, "published_date") or field(item, "fetched_date")
    if not value:
        return True
    try:
        return (date.today() - date.fromisoformat(str(value)[:10])).days <= days
    except ValueError:
        return True


# ---------------------------------------------------------------------------
# Page shell
# ---------------------------------------------------------------------------
TIME_SCRIPT = """<script>
  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function relDate(iso){
    const parsed = new Date(iso + "T00:00:00");
    if (isNaN(parsed)) return "";
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const delta = Math.round((today - parsed) / 86400000);
    if (delta <= 0) return "today";
    if (delta === 1) return "yesterday";
    if (delta < 7) return delta + "d ago";
    if (delta < 30) return Math.floor(delta / 7) + "w ago";
    return MONTHS[parsed.getMonth()] + " " + parsed.getDate() + ", " + parsed.getFullYear();
  }
  function hydrateTimes(root){
    (root || document).querySelectorAll("time.rel[datetime]").forEach(el => {
      const label = relDate(el.getAttribute("datetime"));
      if (label) el.textContent = label;
    });
  }
  document.addEventListener("DOMContentLoaded", () => hydrateTimes());
</script>"""


def document(site: dict, *, page_title: str, active: str, main_html: str, body_script: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(page_title)}</title>
  <meta name="description" content="{escape(site.get("description", ""))}">
  {FONTS}
  <style>{SITE_CSS}</style>
</head>
<body>
{header_html(site, active)}
{main_html}
{footer_html(site)}
{TIME_SCRIPT}
{body_script}
</body>
</html>
"""


def header_html(site: dict, active: str) -> str:
    name = escape(site.get("name", "HST Intelligence"))
    links = "".join(
        f'<a href="{href}"{" class=" + chr(34) + "active" + chr(34) if href == active else ""}>{escape(label)}</a>'
        for href, label in NAV
    )
    return f"""<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="index.html"><span class="br">[</span>{name}<span class="br">]</span></a>
    <nav class="nav">{links}</nav>
  </div>
</header>"""


def footer_html(site: dict) -> str:
    name = escape(site.get("name", "HST Intelligence"))
    return f"""<footer class="site-footer">
  <div class="footer-inner">
    <span>{name} · heat shrink tubing radar</span>
    <span><a href="archive.html">Archive</a> &nbsp;/&nbsp; <a href="weekly.html">Weekly</a> &nbsp;/&nbsp; <a href="materials.html">Materials</a> &nbsp;/&nbsp; <a href="products.html">Products</a> &nbsp;/&nbsp; <a href="regulatory.html">Regulatory</a></span>
  </div>
</footer>"""


# ---------------------------------------------------------------------------
# Index — ranked feed with category tab filtering
# ---------------------------------------------------------------------------
def render_index(config: dict, items: list, latest_weekly=None) -> str:
    site = config["site"]
    tagline = site.get("tagline") or site.get("description", "")

    scoring = config.get("scoring", {})
    # Per-card "heat" badge highlights on relevance; the featured section needs BOTH bars.
    high_threshold = int(scoring.get("high_relevance_score", scoring.get("high_quality_score", 80)))
    high_quality = int(scoring.get("high_quality_score", 80))
    terms = boost_terms(config)
    # Industry first, mirroring pipeline/run.py's prefilter — the reader is a tubing engineer,
    # and a vendor launch or a standards change outranks a journal paper for them.
    ranked = sorted(items, key=lambda it: (0 if is_industry(it) else 1, 0 if is_technical(it, terms) else 1, *rank_key(it)))
    feed_items = ranked[:INDEX_LIMIT]

    def is_high_signal(it) -> bool:
        return (
            _num(field(it, "relevance_score")) >= high_threshold
            and _num(field(it, "quality_score")) >= high_quality
        )

    high = [it for it in feed_items if is_high_signal(it)]
    rest = [it for it in feed_items if not is_high_signal(it)]

    # category counts for the tab bar
    counts: dict[str, int] = {}
    for item in feed_items:
        counts[canonical_theme(field(item, "theme"))] = counts.get(canonical_theme(field(item, "theme")), 0) + 1
    tabs = [f'<button class="tab is-active" data-filter="all">All <span class="tab-n">{len(feed_items)}</span></button>']
    for theme in CANONICAL_THEMES + (["Other"] if counts.get("Other") else []):
        if counts.get(theme):
            tabs.append(f'<button class="tab" data-filter="{escape(theme)}">{escape(theme)} <span class="tab-n">{counts[theme]}</span></button>')
    tabs_html = "".join(tabs)

    sections = []
    if high:
        sections.append(render_section(f"High signal &middot; rel {high_threshold}+ &amp; qual {high_quality}+", high, high_threshold))
    if rest:
        sections.append(render_section("More this week" if high else "This week", rest, high_threshold))
    cards = "\n".join(sections) or '<p class="empty">No included items yet.</p>'
    latest_date = time_html(field(feed_items[0], "published_date") or field(feed_items[0], "fetched_date")) if feed_items else "—"

    hero = f"""<section class="hero">
    <p class="eyebrow"><span class="br">[</span> heat shrink tubing radar <span class="br">]</span></p>
    <h1>The week's <em>signal</em> in heat&nbsp;shrink&nbsp;tubing.</h1>
    <p class="lede">{escape(tagline)}</p>
    <div class="statline">
      <div class="stat"><b>{len(items)}</b><span>tracked</span></div>
      <div class="stat"><b>{len([t for t in counts if t != 'Other'])}</b><span>categories</span></div>
      <div class="stat"><b>{latest_date}</b><span>latest</span></div>
    </div>
  </section>"""

    more = ""
    if len(items) > len(feed_items):
        more = f'<p style="text-align:center;margin:26px 0 0"><a class="weekly-link" href="archive.html">Browse all {len(items)} developments in the archive &rarr;</a></p>'

    main = f"""<main class="wrap">
  {hero}
  {render_weekly_preview(latest_weekly)}
  <div class="tabs" role="tablist">{tabs_html}</div>
  <section class="feed" id="feed">{cards}{more}</section>
  <p class="empty" id="no-match" hidden>No developments in this category yet.</p>
</main>"""

    script = """<script>
    const tabs = document.querySelectorAll('.tab');
    const cards = document.querySelectorAll('#feed .card');
    const noMatch = document.querySelector('#no-match');
    tabs.forEach(tab => tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('is-active'));
      tab.classList.add('is-active');
      const filter = tab.dataset.filter;
      let shown = 0;
      cards.forEach(card => {
        const match = filter === 'all' || card.dataset.theme === filter;
        card.hidden = !match;
        if (match) shown++;
      });
      if (noMatch) noMatch.hidden = shown !== 0;
    }));
  </script>"""

    return document(site, page_title=f'{site.get("name", "HST Intelligence")} — heat shrink tubing', active="index.html", main_html=main, body_script=script)


# ---------------------------------------------------------------------------
# Archive — search + filters
# ---------------------------------------------------------------------------
def render_archive(config: dict, items: list) -> str:
    site = config["site"]
    sources = option_list(sorted({item["source_name"] for item in items if field(item, "source_name")}))
    present = {canonical_theme(field(item, "theme")) for item in items}
    theme_values = [t for t in CANONICAL_THEMES if t in present] + (["Other"] if "Other" in present else [])
    themes = "".join(f'<option value="{escape(t)}">{escape(t)}</option>' for t in theme_values)
    cards = "\n".join(render_card(item) for item in items) or '<p class="empty">No included items yet.</p>'

    main = f"""<main class="wrap">
  <section class="page-head">
    <p class="eyebrow"><span class="br">[</span> full archive <span class="br">]</span></p>
    <h1>Archive</h1>
    <p>Search and filter every tracked development.</p>
  </section>
  <section class="toolbar">
    <label>Search<input id="search" type="search" autocomplete="off" placeholder="Keyword, author, method…"></label>
    <label>Source<select id="source"><option value="">All sources</option>{sources}</select></label>
    <label>Category<select id="theme"><option value="">All categories</option>{themes}</select></label>
  </section>
  <p id="result-count" class="result-count">{len(items)} items</p>
  <section id="items" class="feed">{cards}</section>
</main>"""

    script = f"""<script>
    const HIGH = {int(config.get("scoring", {}).get("high_relevance_score", config.get("scoring", {}).get("high_quality_score", 80)))};
    const items = {json_for_script([archive_item(item) for item in items])};
    const search = document.querySelector("#search");
    const source = document.querySelector("#source");
    const theme = document.querySelector("#theme");
    const count = document.querySelector("#result-count");
    const container = document.querySelector("#items");

    function text(v){{ return v == null ? "" : String(v); }}
    function esc(v){{ return text(v).replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c])); }}
    function meter(score){{
      const n = Math.max(1, Math.min(5, Math.round(score/20)));
      let bars = "";
      for (let i=1;i<=5;i++) bars += `<i class="${{i<=n?'on':''}}"></i>`;
      const high = score >= HIGH;
      return `<span class="signal ${{high?'signal-high':''}}" title="Score ${{score}}/100">${{bars}}<span class="signal-num">${{score}}</span></span>`;
    }}
    function renderItem(it){{
      const why = it.why_it_matters ? `<div class="why"><b>Why it matters</b>${{esc(it.why_it_matters)}}</div>` : "";
      const body = (it.summary || it.abstract) ? `<p class="summary">${{esc(it.summary || it.abstract)}}</p>` : "";
      const when = it.date_iso
        ? `<time class="rel" datetime="${{esc(it.date_iso)}}">${{esc(relDate(it.date_iso))}}</time>`
        : esc(it.date_display);
      return `<article class="card" data-theme="${{esc(it.theme)}}">
  <div class="card-top"><span class="chip">${{esc(it.theme)}}</span>${{meter(it.score)}}</div>
  <h3 class="card-title"><a href="${{esc(it.url)}}" target="_blank" rel="noopener">${{esc(it.title)}}</a></h3>
  <p class="card-meta"><span class="src">${{esc(it.source_name)}}</span><span class="sep">/</span><span>${{when}}</span></p>
  ${{body}}
  ${{why}}
</article>`;
    }}
    function render(){{
      const q = search.value.trim().toLowerCase();
      const filtered = items.filter(it => {{
        const hay = [it.title,it.summary,it.abstract,it.why_it_matters,it.theme,it.source_name].map(text).join(" ").toLowerCase();
        return (!q || hay.includes(q)) && (!source.value || it.source_name === source.value) && (!theme.value || it.theme === theme.value);
      }});
      count.textContent = `${{filtered.length}} item${{filtered.length === 1 ? "" : "s"}}`;
      container.innerHTML = filtered.length ? filtered.map(renderItem).join("") : '<p class="empty">No matching items.</p>';
    }}
    search.addEventListener("input", render);
    source.addEventListener("change", render);
    theme.addEventListener("change", render);
  </script>"""

    return document(site, page_title=f'{site.get("name", "HST Intelligence")} — Archive', active="archive.html", main_html=main, body_script=script)


def archive_item(item) -> dict:
    return {
        "title": item["title"],
        "url": item["url"],
        "source_name": item["source_name"],
        "theme": canonical_theme(field(item, "theme")),
        "summary": field(item, "summary"),
        "abstract": field(item, "abstract"),
        "why_it_matters": field(item, "why_it_matters"),
        "date_iso": _iso_or_none(field(item, "published_date") or field(item, "fetched_date")),
        "date_display": relative_date(field(item, "published_date") or field(item, "fetched_date")),
        "score": score_int(field(item, "relevance_score")) or 0,
    }


# ---------------------------------------------------------------------------
# Shared card
# ---------------------------------------------------------------------------
def render_section(label: str, items: list, high_threshold: int = 80) -> str:
    cards = "\n".join(render_card(item, high_threshold) for item in items)
    return f'<section class="date-group"><h2 class="section-label"><span class="br">[</span> {label} <span class="br">]</span></h2>{cards}</section>'


def render_card(item, high_threshold: int = 80) -> str:
    url = field(item, "url") or ""
    title = field(item, "title") or ""
    src = field(item, "source_name") or ""
    when = time_html(field(item, "published_date") or field(item, "fetched_date"))
    summary = field(item, "summary") or field(item, "abstract") or ""
    why = field(item, "why_it_matters") or ""
    theme = canonical_theme(field(item, "theme"))

    body = f'<p class="summary">{escape(summary)}</p>' if summary else ""
    why_html = f'<div class="why"><b>Why it matters</b>{escape(why)}</div>' if why else ""
    return f"""<article class="card" data-theme="{escape(theme)}">
  <div class="card-top"><span class="chip">{escape(theme)}</span>{signal_html(field(item, "relevance_score"), high_threshold)}</div>
  <h3 class="card-title"><a href="{escape(url)}" target="_blank" rel="noopener">{escape(title)}</a></h3>
  <p class="card-meta"><span class="src">{escape(src)}</span><span class="sep">/</span><span>{when}</span></p>
  {body}
  {why_html}
</article>"""


def signal_html(value, high_threshold: int = 80) -> str:
    n = signal_level(value)
    num = score_int(value)
    bars = "".join(f'<i class="{"on" if i <= n else ""}"></i>' for i in range(1, 6))
    high = num is not None and num >= high_threshold
    cls = "signal signal-high" if high else "signal"
    label = f'<span class="signal-num">{num}</span>' if num is not None else ""
    return f'<span class="{cls}" title="Score {num if num is not None else "?"}/100">{bars}{label}</span>'


def signal_level(value) -> int:
    try:
        return max(1, min(5, round(float(value) / 20)))
    except (TypeError, ValueError):
        return 1


def score_int(value):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Weekly synthesis
# ---------------------------------------------------------------------------
def render_weekly(config: dict, summaries: list) -> str:
    site = config["site"]
    entries = "\n".join(render_weekly_entry(summary) for summary in summaries) or '<p class="empty">No weekly syntheses yet.</p>'
    main = f"""<main class="wrap">
  <section class="page-head">
    <p class="eyebrow"><span class="br">[</span> weekly synthesis <span class="br">]</span></p>
    <h1>Weekly Synthesis</h1>
    <p>Trends across the week, clustered by theme.</p>
  </section>
  <section class="feed">{entries}</section>
</main>"""
    return document(site, page_title=f'{site.get("name", "HST Intelligence")} — Weekly synthesis', active="weekly.html", main_html=main)


def render_weekly_preview(summary) -> str:
    if summary is None:
        return ""
    return f"""<section class="card" style="padding:22px 24px">
  <p class="eyebrow" style="margin-bottom:8px"><span class="br">[</span> latest weekly synthesis <span class="br">]</span></p>
  <p class="weekly-meta">{escape(summary["week_start"])} &mdash; {escape(summary["week_end"])}</p>
  <div class="prose prose-clip">{markdown_to_html(summary["synthesis_md"])}</div>
  <a class="weekly-link" href="weekly.html">Read the full synthesis &rarr;</a>
</section>"""


def render_weekly_entry(summary) -> str:
    return f"""<article class="card" style="padding:24px">
  <h2 style="font-family:var(--display);margin:0 0 4px;font-size:1.25rem;letter-spacing:-.02em">{escape(summary["week_start"])} &mdash; {escape(summary["week_end"])}</h2>
  <p class="weekly-meta">Generated {escape(summary["generated_at"])}</p>
  <div class="prose">{markdown_to_html(summary["synthesis_md"])}</div>
</article>"""


# ---------------------------------------------------------------------------
# Weekly web-search sections — Materials, Notable Products, Regulatory Watch.
#
# All three are the same page: a table of rows compiled by the weekly run, an
# empty state when the section hasn't run (or the run had no API key), and the
# compiled-week note. Only the columns differ, so they share one renderer.
# `columns` is (header, payload key, css class); the css class drives the two
# emphasis styles already in table.matreq — "app" for the row's subject and
# "chal" for the consequence/challenge column.
# ---------------------------------------------------------------------------
def render_section_page(
    config: dict,
    section,
    *,
    page: str,
    eyebrow: str,
    heading: str,
    blurb: str,
    payload_key: str,
    columns: list[tuple[str, str, str]],
) -> str:
    site = config["site"]
    rows = (section or {}).get("payload", {}).get(payload_key, []) if section else []
    when = ""
    if section:
        when = f'<p class="section-note">Compiled {escape(str(section.get("week_start", "")))} &mdash; {escape(str(section.get("week_end", "")))}</p>'

    if rows:
        head = "".join(f"<th>{escape(header)}</th>" for header, _, _ in columns) + "<th>Source</th>"
        body = "".join(
            "    <tr>"
            + "".join(
                f'<td{f" class={chr(34)}{css}{chr(34)}" if css else ""}>{escape(str(row.get(key, "")))}</td>'
                for _, key, css in columns
            )
            + f"<td>{_source_link(row.get('source_url'))}</td></tr>"
            for row in rows
        )
        content = f"""<div class="table-wrap"><table class="matreq">
  <thead><tr>{head}</tr></thead>
  <tbody>
{body}
  </tbody>
</table></div>"""
    else:
        content = f'<p class="empty">No {heading.lower()} compiled yet — this section is generated on the weekly run.</p>'

    main = f"""<main class="wrap">
  <section class="page-head">
    <p class="eyebrow"><span class="br">[</span> {escape(eyebrow)} <span class="br">]</span></p>
    <h1>{escape(heading)}</h1>
    <p>{escape(blurb)}</p>
    {when}
  </section>
  <section class="feed">{content}</section>
</main>"""
    return document(
        site,
        page_title=f'{site.get("name", "HST Intelligence")} — {heading}',
        active=page,
        main_html=main,
    )


def render_materials(config: dict, section) -> str:
    return render_section_page(
        config,
        section,
        page="materials.html",
        eyebrow="materials",
        heading="Materials",
        blurb="Each tubing family mapped to its base polymer, crosslinking route, property targets, and the open challenge.",
        payload_key="materials",
        columns=[
            ("Application", "application", "app"),
            ("Material class", "material_class", ""),
            ("Key properties", "key_properties", ""),
            ("Open challenge", "open_challenge", "chal"),
        ],
    )


def render_products(config: dict, section) -> str:
    return render_section_page(
        config,
        section,
        page="products.html",
        eyebrow="notable products",
        heading="Notable Products",
        blurb="Heat shrink tubing launched recently — what it is made of, what it is for, and when it was announced.",
        payload_key="products",
        columns=[
            ("Product", "product", "app"),
            ("Manufacturer", "manufacturer", ""),
            ("Material / construction", "material_construction", ""),
            ("Application", "application", ""),
            ("Announced", "announced", "chal"),
        ],
    )


def render_regulatory(config: dict, section) -> str:
    return render_section_page(
        config,
        section,
        page="regulatory.html",
        eyebrow="regulatory watch",
        heading="Regulatory Watch",
        blurb="Standards and regulatory movement, and what each one changes for a tubing manufacturer.",
        payload_key="regulations",
        columns=[
            ("Regulation", "regulation", "app"),
            ("Body", "body", ""),
            ("Change", "change", ""),
            ("Status / date", "status_effective_date", ""),
            ("Impact on HST", "hst_impact", "chal"),
        ],
    )


def _source_link(url) -> str:
    if not url:
        return "&mdash;"
    return f'<a href="{escape(str(url))}" target="_blank" rel="noopener">link</a>'


def markdown_to_html(markdown: str) -> str:
    lines: list[str] = []
    bullets: list[str] = []

    def flush():
        if bullets:
            lines.append("<ul>" + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("### "):
            flush()
            lines.append(f"<h3>{render_inline(format_theme(line[4:]))}</h3>")
        elif line.startswith("## "):
            flush()
            lines.append(f"<h2>{render_inline(format_theme(line[3:]))}</h2>")
        elif line.startswith("- "):
            bullets.append(render_inline(line[2:]))
        else:
            flush()
            lines.append(f"<p>{render_inline(line)}</p>")
    flush()
    return "\n".join(lines)


_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def render_inline(text: str) -> str:
    out = escape(text)
    out = _LINK_RE.sub(lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">{m.group(1)}</a>', out)
    out = _BOLD_RE.sub(r"<b>\1</b>", out)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def field(item, key: str):
    try:
        return item[key]
    except (KeyError, IndexError):
        return None


_CANON_LOOKUP = {re.sub(r"[^a-z0-9]+", "", t.lower()): t for t in CANONICAL_THEMES}


def canonical_theme(raw) -> str:
    """Map a stored theme (fixed label or legacy free-text) to one of the 8 themes or 'Other'."""
    if not raw:
        return "Other"
    key = re.sub(r"[^a-z0-9]+", "", str(raw).lower())
    if key in _CANON_LOOKUP:
        return _CANON_LOOKUP[key]
    text = str(raw).lower()
    if any(t in text for t in ("standard", "regulat", "compliance", "pfas restriction", "reach", "rohs", "ul 224", "mil-", "iec ", "sae ", "iso ")):
        return "Standards & Regulatory"
    if any(t in text for t in ("characteriz", "testing", "test method", "dsc", "tga", "ftir", "dma", "aging", "failure analysis")):
        return "Characterization & Testing"
    if any(t in text for t in ("manufactur", "process", "extrus", "crosslink", "cross-link", "e-beam", "irradiat", "production")):
        return "Manufacturing & Processing"
    if any(t in text for t in ("product", "launch", "release")):
        return "Products & Launches"
    if any(t in text for t in ("material", "formulation", "polymer", "resin", "fluoropolymer", "additive", "chemistr")):
        return "Materials & Formulations"
    if any(t in text for t in ("application", "medical", "aerospace", "automotive", "ev ", "energy", "industrial", "telecom")):
        return "Applications"
    if any(t in text for t in ("market", "supply", "supplier", "pricing", "capacity", "acquisition", "business")):
        return "Market & Supply Chain"
    if any(t in text for t in ("academic", "research", "r&d", "university", "journal", "paper")):
        return "Academic R&D"
    return "Other"


def boost_terms(config: dict) -> list[str]:
    targeting = config.get("targeting", {}) if isinstance(config, dict) else {}
    return [str(term).lower() for term in targeting.get("technical_boost_terms", [])]


# Kept in sync with pipeline/run.py INDUSTRY_SOURCE_TYPES.
INDUSTRY_SOURCE_TYPES = frozenset({"company_news", "web_news", "google_news", "org_blogs"})


def is_industry(item) -> bool:
    return field(item, "source_type") in INDUSTRY_SOURCE_TYPES


def is_technical(item, terms: list[str]) -> bool:
    if not terms:
        return False
    haystack = " ".join(str(field(item, k) or "") for k in ("title", "summary", "abstract", "theme")).lower()
    return any(term in haystack for term in terms)


def rank_key(item) -> tuple[float, float]:
    return (-_num(field(item, "relevance_score")), -_num(field(item, "quality_score")))


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _iso_or_none(value):
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None


def relative_date(value) -> str:
    parsed = _parse_date(value)
    if parsed is None:
        return str(value or "")
    delta = (date.today() - parsed).days
    if delta <= 0:
        return "today"
    if delta == 1:
        return "yesterday"
    if delta < 7:
        return f"{delta}d ago"
    if delta < 30:
        weeks = delta // 7
        return f"{weeks}w ago"
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def time_html(value) -> str:
    """Relative date carrying its absolute date, so the browser can re-derive it.

    The site is rebuilt weekly but read all week, so a string baked in at build
    time drifts. TIME_SCRIPT recomputes from the datetime attribute on load; the
    rendered text is the no-JS fallback.
    """
    parsed = _parse_date(value)
    if parsed is None:
        return escape(str(value or ""))
    return f'<time class="rel" datetime="{parsed.isoformat()}">{escape(relative_date(value))}</time>'


def option_list(values: list[str], *, labeler=None) -> str:
    labeler = labeler or (lambda value: value)
    return "".join(f'<option value="{escape(value)}">{escape(labeler(value))}</option>' for value in values)


def format_theme(value: str) -> str:
    return (value or "").replace("_", " ")


def json_for_script(value) -> str:
    return json.dumps(value, sort_keys=True).replace("</", "<\\/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the HST Intelligence static site")
    parser.add_argument("--config", default="targeting.yaml")
    parser.add_argument("--db", default="data/tracker.db")
    parser.add_argument("--output", default="public")
    args = parser.parse_args()
    build_site(config_path=args.config, db_path=args.db, output_dir=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
