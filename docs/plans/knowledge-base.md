# Plan: knowledge base v1 (RAG for designing FTC robots)

Goal: when a person says "I want a shooter for BIOBUZZ, here's our old one, it needs X, watch out for Y, it has to fit in this space", Claude searches past robots, mechanisms, ideas, parts and rules, proposes 2–3 concepts, and then builds the chosen one with the assembly tools ([assembly-tools.md](assembly-tools.md)).

**v1 is done when** the four test tasks at the bottom run with the knowledge base and do better than without it (fewer tool calls and errors, and the design passes the rule check).

Rules from CLAUDE.md apply: keep it small, fast, and cheap in tokens. Use the 80/20 rule. Spike before building.

Legend: ✅ checked by a spike on 2026-10-19 · ❓ still to spike · ⏳ in progress

---

## Decisions (settled with the user, 2026-10-19)

| Topic | Decision |
|---|---|
| Storage | **Files in git (`kb/`) are the source of truth.** SQLite (FTS5 + plain tables) is a throwaway index, rebuilt when files change. Only one person uses it, through git. |
| Search | Exact SQL filters (parts, rule numbers, facets) + FTS5 keyword search (BM25). **No vectors in v1.** Add embeddings only for book sections, and only if the test tasks show book searches missing. |
| Main unit | The **mechanism card**. Robots break into mechanisms, and ideas are deduplicated across robots. **Parts are never stored per robot.** |
| Sources of robots | Public CAD from other teams: **FTC CAD Base** and **Open Vault**, mostly Onshape. The team itself builds only 1–2 robots a season, so most of the database is other teams' work. |
| Review | **The user approves every robot** on the review page. Drafting runs unattended ahead of review. |
| Rating | From FTC Scout: 70% OPR percentile + 30% how far the team advanced. **No awards** (the user considers them biased). Offseason robots get a flat 0.9×. |
| Books | **gm0** first, then the **BIOBUZZ competition manual**. |
| Vendor scrape | **goBILDA only**: metadata to `parts.csv`, with STEP files downloaded on first use into a cache outside git. |
| Manufacturing | Laser cutting (wood, aluminum), FDM printing, wood for prototypes. Little CNC. |

## Spike results (2026-10-19)

| # | Finding |
|---|---|
| K1 | ✅ **Onshape API** works with basic auth (keys in `~/.config/fusion-mcp/onshape.env`, outside the repo). On a public BIOBUZZ robot: document info <1 s, assembly tree 1 s, flat BOM (`bom?indented=false&multiLevel=true`) 3 s, shaded-view PNG 11 s. |
| K2 | ✅ **Mechanisms sit at level 2** of the tree (`Chassis and Intake → Drivetrain assembly · Flower Intake · Front Roller`). Generic names (`Assembly 1`, `Part 2`) are noise. |
| K3 | ✅ **The BOM "Part number" field is empty.** COTS parts are named in Onshape's FTC library style with a vendor suffix: `104mm Mecanum Wheel (GB)`, `9t Pinion Gear (SC)`, `Control Hub (REV)`, `Mini Servo (AXON)`. goBILDA matching has to go **name → SKU**. The names alone fill in most facets. |
| K4 | ✅ Each mechanism subassembly renders on its own (`/assemblies/d/{did}/m/{mv}/e/{eid}/shadedviews`, about 10 s each, run in parallel). ❌ **A subassembly linked from a private document returns 403.** Fall back to the whole-robot render and flag it. |
| K5 | ✅ Some mechanisms aren't subassemblies (a ramp made of loose parts in the chassis). Mark them "(inferred)" for review. |
| K6 | ✅ **FTC CAD Base** embeds its whole catalog in the page's Next.js payload (`self.__next_f.push` strings → `{"id":…,"url":…,"season":…,"primaryCategory":…,"tags":[…]}`). It has 259 FTC entries: **109 full robots** (96 Onshape) and **150 mechanism-only entries**. **202 of 259 have no season, and none has a team-number field.** |
| K7 | ✅ **Open Vault** is server-rendered HTML: about 6 robots and 17 mechanisms over 7 category pages. Every entry has a team number, season, "used in competition" and a description. Licence: CC BY-NC-SA 4.0. |
| K8 | ✅ **FTC Scout GraphQL** (`api.ftcscout.org/graphql`) needs no key. `teamByNumber(number).quickStats(season).tot{value rank}, count`, `events(season){event{type} stats{rank}}`. Event types include `FIRSTChampionship`, `Championship`, `Premier`, `SuperQualifier`, `Qualifier`, `LeagueMeet`, `LeagueTournament`. |
| K9 | ✅ **gm0** lives on GitHub (`gamemanual0/gm0`): 128 `.rst` pages, about 776 KB. Licence CC BY-NC 2.0 (fine for personal, non-commercial use; keep attribution). |
| K10 | ✅ **BIOBUZZ manual** TU05 (2026-10-15, 175 pages) is saved to `kb/rules/2026-27/`. Every rule starts on its own line with its ID (`R102 *…`), so splitting per rule is trivial. |
| K11 | ✅ **The review page** (private artifact, database collection `robots`) round-trips a draft → approval. The first robot was approved without edits. |
| K12 | ✅ Pilot (2026-10-20): **7 of 17 CAD Base links return 403** on the assembly. Some documents answer `GET /documents` with `public: false` (link-shared); the API key can't read a link-shared assembly. Failed calls aren't logged (they don't count against the cap). |
| K13 | ✅ A robot costs **~4 calls + 1 per rendered mechanism** (pilot: 69 calls for 10 drafts + 7 failures, ~7 per robot). Skipping `GET /documents` when the title has a team number saves 1. |
| K14 | ✅ **Mechanism layout varies a lot.** Some CADs nest mechanisms at level 1 (`Launcher`, `Turret`), some at level 2, some put whole mechanisms as loose parts at the root, and one puts the entire robot inside `drivetrain`. Shooter + turret are usually one subassembly; one render serves both cards. |
| K15 | ✅ **Part names differ by library.** Besides `… (GB)`, many robots use goBILDA's full catalog names with SKUs (`5203 Series Yellow Jacket … (19.2:1 Ratio …) 5203-2402-0019`). Motor names sit on the **assembly instance**, not on parts (`Motor Part`, `Motor Sleeve`). Gear ratios read straight from the SKU name. Some teams use simplified motor models with no rpm. |
| K16 | ✅ **Team numbers hide in renders.** A CAD Base entry titled "2025-2026" (owner "2 Kan") showed 13581 on its number plate. Check the robot render for a number plate before asking. |
| K17 | ✅ **Loose-part mechanisms can be rendered.** Onshape can't hide parts in a shaded view, but a STEP export (≈6 calls, 55 MB for a full robot) imports into Fusion in ~20 s with positions intact. Turning occurrences off and saving the viewport gives one render per mechanism. Parts are assigned by name + position (COTS transforms in `assembly.json`). The user's split rules are in the brief. Each translation poll is a billed call: 200 MB robots take 3–6 min, so poll every 60 s (≈8–10 calls per robot). A 200 MB STEP imports in ~50 s, past the 30 s bridge timeout, but finishes; check with a second call. Helper: `scripts/kb/fusion_render.py`. |

---

## Layout

```
kb/
├── lessons.md                # capped ~150 lines: design tricks + workflow gotchas. Loaded every session.
├── design_rules.md           # loaded every session: tolerances and rules for laser (wood/alu), FDM, wood prototypes
├── ideas.csv                 # id, mechanism, text, tags, seen_in (robot ids), source
├── robots/<robot-id>/
│   ├── robot.md              # robot card (frontmatter + short body)
│   ├── <mechanism-key>.md    # one mechanism card each
│   └── *.jpg                 # 1 robot render + 1 per mechanism, ~800 px
├── books/<slug>/NN-<section>.md
├── parts/parts.csv           # goBILDA scrape; STEP cache in ~/.fusion-mcp/step-cache/ (outside git)
├── rules/2026-27/            # ✅ competition-manual-TU05.pdf, constraints.json
└── ingest/
    ├── queue.csv             # every source entry + its pipeline status
    └── drafts/<robot-id>/    # renders + raw API JSON while waiting for review (gitignored)
.kb-index.sqlite              # gitignored, rebuilt from kb/
```

Our own designs live in `robots/` too, with `source: ours`, plus the recipe sections (brief, decisions and why, results).

## Cards

### Robot card (`robot.md`, ~100 tokens)
**Frontmatter format (what `kb.py` parses):** one `key: value` per line, no nesting or multi-line YAML. Structured values are written as **JSON** on one line. `id`, `title`, `name`, `type`, `season` and `source` always stay text (so `9.10` doesn't become `9.1`).
```
id: cb-374cd425e3bf5a9555f301d2
title: Biobuzz robot by Drizzy
entry: robot
team: {"number": null, "name": null}
season: 2026-27 BIOBUZZ
source: {"site": "FTC CAD Base", "url": "…", "owner": "…", "licence": "…"}
rating: {"basis": "unknown", "multiplier": 1.0, "detail": "…", "fetched": "2026-10-19"}
mechanisms: ["drivetrain", "front-roller"]
```
`id` is `<site>-<onshape doc id>`, so the same document on both sites is one robot. `entry: mechanism` marks a source entry that is a single mechanism (the card is still the robot card). `source.site: "ours"` marks our own designs (ranked higher).
Body: a 1–2 sentence summary.

### Mechanism card (`<key>.md`, ~300 tokens, capped)
Shared fields (same frontmatter format; `facets` and `rating` as JSON, the rating copied from the robot so mechanisms rank by it): `type`, `name`, `path` (subassembly path), `facets`, `rating` (robot multiplier × `bias`; bias lower 0.85 / higher 1.15, set in review), `season`, `motors`, `servos`, `materials`, `notable` (≤ 80 words), `ideas` (ids), `variant_of`.

Types with their own facets (fixed choices in brackets):

| Type | Facets |
|---|---|
| drivetrain | drive_type [mecanum, tank, swerve, h-drive, other], wheel, motor_count, motor, gear_ratio, odometry [pods, dead wheels, none, other], frame [channel, plates, custom], material |
| intake | intake_type [roller, compliant wheels, surgical tubing, claw-style, other], width_mm, motors, servos, deploy [fixed, pivot, slide], passes_to [shooter, storage, claw, transfer, other] |
| shooter | shooter_type [single flywheel, double flywheel, counter roller, catapult, other], wheel_diameter_mm, wheel_material, compression_mm, motor_count, motor_rpm, gear_ratio, hood [fixed, adjustable, none], feeder, game_piece [POLLEN, NECTAR, other] |
| turret | drive [gear, belt, chain, other], actuator [motor, servo], bearing [lazy susan, slewing ring, custom], homing [encoder, limit switch, hard stop, none], carries. *No rotation range: wires limit it, and wires are never in the CAD.* |
| transfer | from, to, method [rollers, belts, gravity ramp, servo kicker, indexer wheel, other], capacity, sensing [color, distance, none], actuators |
| claw | actuation [servo, linear servo, passive], grip [pads, fingers, hooks, other], dof, material |
| power_transmission | purpose, switching [servo dog shift, ratchet, differential, other], input_motors, outputs, ratios, locking |

Slide/extension, arm, hang, outtake and other stay generic (no facets) until there are about 10 examples of a type.

### Anti-bloat rules (`kb_save_*` tools refuse cards that break them)
1. Fixed choices instead of prose. Free text only in `notable` (≤ 80 words).
2. Write only what differs from normal for that type.
3. Ideas are deduplicated: a known idea gains a robot id in `seen_in` instead of new text.
4. No raw CAD in git: store the link and subassembly path.
5. One render per mechanism, about 800 px JPEG.
6. `variant_of`: a team's mechanism carried over from last year gets a short card listing only what changed.

Size estimate: ~115 robots × ~5 mechanisms ≈ 600 cards × 300 tokens ≈ 180k tokens in total, never loaded at once.

## Rating

```
opr_pct     = 1 − quickStats.tot.rank / quickStats.count
advancement = 1.0 if any event.type == FIRSTChampionship
              0.5 if any event.type in {Championship, Premier, SuperQualifier}
              0   otherwise
score       = 0.7·opr_pct + 0.3·advancement
multiplier  = 0.8 + 0.5·score            (0.8 – 1.3)
```
- Offseason robot: **0.9×** flat (teams skip steps on offseason builds).
- Team or season unknown: **1.0×**, neutral. Unknown is not the same as offseason; the reviewer decides which.
- It rates the team, not the mechanism, so it's a ranking multiplier and never a filter. Store the raw stats and the fetch date; a refresh command recomputes them during the season.
- **Design feedback** (`kb_feedback`, 2026-10-20): when the user accepts or rejects a part Claude designed from KB entries, Claude records the responsible entries, the verdict and the reason in `kb/feedback.csv` (`date, entry, verdict, design, reason`). Each like is +0.1 and each dislike −0.1 on that entry, clamped to 0.7–1.3×, multiplied onto the rating above. Only verdicts move the rank; how often an entry is opened doesn't (that would feed back on whatever already ranks first). Hit lines show "used in N designs: X liked, Y disliked".
- Season → FTC Scout year: BIOBUZZ 2026, DECODE 2025, INTO THE DEEP 2024, CENTERSTAGE 2023, POWERPLAY 2022, FREIGHT FRENZY 2021, ULTIMATE GOAL 2020, SKYSTONE 2019.

## Search and MCP tools

All `kb_*` tools are handled inside `server.py` and never sent to the add-in.

| Tool | What it does |
|---|---|
| `kb_search(query?, kind?, type?, season?, facets?, limit=8)` ✅ | FTS5 (porter stemming, synonyms, prefix match) over robots, mechanisms, ideas, rules and book sections, plus exact filters. One line per hit (~30 tokens). Replaces the planned `kb_ideas` (`kind: "idea"`) and `kb_rule` (`kind: "rule"`), to keep the tool list short |
| `kb_get(id)` ✅ | The full card, rule or book section. A robot lists its mechanisms. An unknown id suggests close ones |
| `kb_find_part(sku? \| name?, type?, length_mm?)` | Exact filters on `parts.csv`; also matches Onshape library names (K3) |
| `check_robot_rules(component?)` | Size cube (R102), expansion box (R105), motor/servo counts (R503), using `get_bounding_box` + `get_bom` |
| `kb_save_design(…)` / `kb_add_lesson(…)` | End of session, for our own designs and lessons. Refuses anything over the caps |

Ranking: BM25 (title 3, body 1, tags 2) × rating multiplier × 1.2 for `source: ours` × 1.1 for the current season × (1 + 0.15·ln(1 + seen_in)) for ideas. Filters run first; with no query, results sort by that boost alone. Mixed-kind queries rank by relevance, so pass `kind: "rule"` when checking rules. Code: `src/fusion360_mcp/kb.py`, `kb_tools.py` (branch `feat/kb-search`, worktree `.worktrees/kb-search`).
`lessons.md`, `design_rules.md` and the current `constraints.json` reach Claude as MCP resources at session start.

## Ingest

### Robots (the big one)
Run by an AI agent following **[robot-ingest-brief.md](robot-ingest-brief.md)**. In short: build the queue from both sites → per robot, fetch tree + BOM + renders through the Onshape API → split into mechanisms → fill facets from library part names → rate with FTC Scout → write a draft to the review page → the user approves → an export step writes approved drafts into `kb/robots/` and `kb/ideas.csv`.

### Books
- **gm0:** read the `.rst` source from GitHub, keep only `common-mechanisms/`, `hardware-components/` and `power-and-electronics/`, split by heading (≤ 600 words per section), one-line summary + tags per section, and pull ideas into `ideas.csv` with `source: gm0`. The version is the commit hash; a re-pull re-reads only changed pages.
- **BIOBUZZ manual:** split per rule ID (R, G, …) into `kb/books/biobuzz-manual/`, and Section 9 (field and game pieces) per heading. When a new team update (TU06…) comes out, download it, re-split, and update `constraints.json`.

### Parts
A goBILDA scraper (`scripts/kb/scrape_gobilda.py`, ❓ spike first: check robots.txt and terms) writes `parts.csv` (sku, name, type, length_mm, dims, hole_pattern, mass_g, price, counts_as, step_url). STEP files are downloaded on first `insert_part` into `~/.fusion-mcp/step-cache/`. A name-match column maps Onshape library names (`… (GB)`) to SKUs.

## Build order

| Step | What | Status |
|---|---|---|
| 1 | Robot review page + first robot drafted and approved | ✅ |
| 2 | Robot ingest: **pilot batch of 10** (BIOBUZZ + DECODE): 10 drafts on the review page 2026-10-20; waiting for the user's review, then adjust the brief | ⏳ |
| 3 | Export approved drafts → `kb/robots/`, `kb/ideas.csv` (`scripts/kb/export_approved.py`; 7 robots, 34 mechanisms, 24 ideas on 2026-10-20) | ✅ |
| 4 | SQLite index + `kb_search` / `kb_get` (branch `feat/kb-search`: 21 tests, live on the 149 manual files, build 35 ms, search ~1.5 ms) | ✅ not merged |
| 5 | BIOBUZZ manual split per rule ✅ (`scripts/kb/split_manual.py` → `kb/books/biobuzz-manual/`: 99 R/G/I rules + 50 sections from 9, 10, 12; E/T/A/C logistics rules skipped) + `check_robot_rules` ❓ (needs assembly tools #11, #12) | ⏳ |
| 6 | gm0 ingest | ❓ |
| 7 | goBILDA scrape + `kb_find_part` + name → SKU matching | ❓ |
| 8 | `lessons.md`, `design_rules.md` (needs real numbers from the team's printers and laser), `kb_save_design` | ❓ |
| 9 | Rest of the robot backlog in batches of ~25 | ❓ |
| 10 | Test tasks, with the knowledge base off and on | ❓ |

## Test tasks
- **A.** "Shooter for BIOBUZZ, here's our old one, fit it in this envelope."
- **B.** A custom FDM-printed intake.
- **C.** A drivetrain inside the 18 in starting cube.
- **D.** Add a subsystem to an existing robot and pass the rule check.

Measure tool calls, errors, and whether the result passes `check_robot_rules`.

## Not in v1
Vectors and Voyage, storing sketches, rule versioning beyond re-pulling the manual, raw tool-call logs, ranking by our own competition outcomes, scraping vendors other than goBILDA.

## Open items
- Onshape API calls are capped at **2,500 per user per year** on the Free/Standard/EDU Student plans (Onshape's limits page). Over the cap, calls fail with 402 until the year resets; more can only be bought through Onshape sales. The backlog needs ≈ 1,400. The ingest agent logs calls and stops at 2,000.
- The Onshape API keys were pasted in a chat. Rotate them once the pipeline is built.
- `design_rules.md` needs the team's real numbers (printer hole tolerance, laser kerf for wood and aluminum).
