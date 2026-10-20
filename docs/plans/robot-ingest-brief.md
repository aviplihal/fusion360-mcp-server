# Brief: ingest public FTC robots into the review queue

You are an AI agent working in the repo `fusion360-mcp-server`. Your job is to turn public FTC robot CAD into **draft robot cards** on the user's review page, so the user can approve them quickly. You don't write anything into `kb/robots/` yet; that happens after approval (see "After review").

Read first: [knowledge-base.md](knowledge-base.md), especially the spike results K1–K11, the card formats, and the rating formula. This brief is the how-to; that plan is the why.

---

## What you have

| Thing | Where |
|---|---|
| Onshape API keys | `~/.config/fusion-mcp/onshape.env` (`ONSHAPE_ACCESS_KEY`, `ONSHAPE_SECRET_KEY`). Basic auth, `https://cad.onshape.com/api/v10`. **Never print the keys, copy them into the repo, or put them in a draft.** |
| Review page | https://claude.ai/artifact/PDXC2H15BL6hTJwngfY6e2. Database collection `robots`, written with the `ArtifactData` tool. Renders are uploaded with the `Artifact` tool (`asset: true`, `url` = the page). |
| FTC Scout | `https://api.ftcscout.org/graphql`, no key |
| Robot sources | FTC CAD Base `https://www.cadbaseftc.com` and Open Vault `https://www.open-vault-ftc.org/cad/<category>` |
| Example of a good draft | Document `cb-374cd425e3bf5a9555f301d2` in the `robots` collection, approved by the user without edits. Read it before drafting anything, and match its style and level of detail. |
| Game context | `kb/rules/2026-27/constraints.json` (POLLEN ball 7.1 cm, NECTAR 9.1 cm, size limits) |

Put scripts in `scripts/kb/` (plain Python 3, standard library first; run with `python3 -I`). Put working files in `kb/ingest/drafts/<robot-id>/`, which is gitignored; add that line to `.gitignore` if it's missing.

## Step 0: build the queue (once)

1. **CAD Base.** Fetch the home page. The catalog is in the `self.__next_f.push([1,"…"])` strings: JSON-decode each string, join them, then `raw_decode` every object that starts with `{"id":"` and has `url` plus `program` or `season`. Keep `program == "FTC"` and `kind == "cad"`.
2. **Open Vault.** Fetch the 7 category pages (`robots`, `drivetrains`, `active-intakes`, `claws`, `outtakes`, `dead-axles`, `power-transmissions`) and parse each entry: title, team number, team name, seasons used, used in competition, description, link.
3. Write **`kb/ingest/queue.csv`** with: `id, site, title, kind (robot|mechanism), category, season, team_number, platform, url, onshape_doc, status, note`.
   - `id` = `cb-<onshape doc id>` or `ov-<onshape doc id>`. If both sites have the same Onshape document, keep **one** row (prefer Open Vault, which has the team number) and note the other site.
   - Non-Onshape entries (Google Drive, GrabCAD, Fusion links): `status = skipped-non-onshape`. They'll be ingested later through Fusion, once `insert_part` exists.
   - `status` values: `queued`, `drafted`, `failed`, `skipped-*`.
4. **Order:** BIOBUZZ, then DECODE, then other named seasons (newest first), then full robots before mechanisms, then "Unspecified / Offseason" last.

## Step 1: per robot

Run several robots in parallel (about 4 at a time). Each robot should take roughly 1 minute of API time.

1. **Fetch** (log every call and stop at the budget; see "Limits"):
   - `GET /documents/{did}` for name and owner: **only when the team is unknown**, since the owner name can hint at the team
   - `GET /assemblies/d/{did}/w/{wid}/e/{eid}` for the tree
   - `GET …/bom?indented=false&multiLevel=true` for parts and quantities
   - `GET …/shadedviews?viewMatrix=isometric&outputWidth=800&outputHeight=600&pixelSize=0` for the whole robot
   - The link's element may be a Part Studio rather than an assembly. If so, look up the document's elements (`/documents/d/{did}/w/{wid}/elements`) and use the top-level assembly; if there are several, take the one named like the robot, and say which in `questions`.
2. **Split into mechanisms.** Walk the tree down from the root until names describe a mechanism (Drivetrain, Intake, Shooter, Turret, Transfer, Claw, Lift/Slides, Arm, Hang, Outtake, PTO/Differential…). Generic names (`Assembly 1`, `Part 2`) aren't mechanisms; look inside them. A mechanism built from loose parts with no subassembly of its own gets `"(inferred)"` in its name and a question.
3. **Render each mechanism** (skip this for mechanism-only entries; their whole-robot render already shows the mechanism) with `/assemblies/d/{did}/m/{documentMicroversion}/e/{elementId}/shadedviews` (600×450), using the instance's own document id, microversion and configuration. **A 403 means the subassembly is linked from a private document:** set `render_url: null`, `render_note: "Render blocked: linked document isn't public."`, and carry on.
4. **Read the parts.** List each mechanism's parts recursively, ignoring screws, nuts and inserts. COTS parts are recognized by their vendor suffix: `(GB)` goBILDA, `(SC)` ServoCity, `(REV)`, `(AXON)`, `(AM)` AndyMark. Use the names to fill facets (wheel type and size, motor model and count, gear and pulley teeth for ratios, bearings, servos).
5. **Fill the card** using the facet lists in the plan. **Use only the fixed choices listed; anything else goes in `notable`.** Don't guess numbers: leave a facet empty rather than inventing it, and say "(check)" when you inferred it. `notable` is ≤ 80 words and only records what's unusual for that type.
6. **Ideas:** 3–8 per robot, one sentence each (≤ 25 words), about a choice another team could reuse. Before adding one, check the ideas in existing drafts (`ArtifactData` `list` on `robots`). If the same idea is already there, reuse its exact text so it can be deduplicated later.
7. **Team and season.** Use the source's fields first. Otherwise look for a 3–5 digit team number in the title, document name or owner, and a season name. If you're guessing, say so in `questions`. If you find nothing, leave them `null` and ask.
8. **Rating** (formula in the plan):
   - Known team and season: query FTC Scout for `quickStats(season)` and `events(season)`. Store `opr_pct`, `opr_rank`, `teams`, the best event type, and the fetch date in `rating`, and put a short human-readable `detail` (e.g. "OPR 79th pct of 7641 · Georgia Championship").
   - Offseason: `basis: "offseason"`, `multiplier: 0.9`.
   - Unknown: `basis: "unknown"`, `multiplier: 1.0`.
9. **Upload the renders** (one `Artifact` call with `asset: true` and `file_paths`, up to 25 files) and use each returned `url` exactly as given.
10. **Write the draft** with `ArtifactData` `set` into `robots/<id>`. For more than 2 robots at once, use `batch`. Fields:
    `title, status: "pending", priority, queued_at, kind, team {number, name} | null, season, source {site, url, owner, onshape_doc, licence}, render_url, summary (1–2 sentences), rating {basis, multiplier, detail, …}, questions [ … ], mechanisms [ {type, name, path, render_url, render_note?, facets {…}, notable} ], ideas [ {text, mechanism, keep: true} ]`.
    `priority`: BIOBUZZ 10, DECODE 8, other seasons 5, offseason/unknown 2. Mechanism-only entries get the same and `kind: "mechanism"` with a single mechanism.
11. Update the row in `queue.csv` to `drafted`, or to `failed` with a short reason.

**Questions** are the most useful thing you write for the reviewer. Ask about everything you weren't sure of, one short sentence each, and nothing you were sure of.

## Tools (built in the pilot)

```
python3 -I scripts/kb/build_queue.py --repo .                 # step 0, keeps existing statuses
python3 -I scripts/kb/queue_status.py next 25                 # next queued ids
export ONSHAPE_RUN_START=<UTC time of the run's first call>   # budget counts from here
python3 -I scripts/kb/onshape_fetch.py fetch <id>             # doc, tree, BOM, robot render + tree summary
python3 -I scripts/kb/onshape_fetch.py tree <id> 2            # compact tree again, no API call
python3 -I scripts/kb/onshape_fetch.py parts <id> "<path>"    # parts under a path ("" = root loose parts)
python3 -I scripts/kb/onshape_fetch.py render <id> "<path>"…  # mechanism renders (1 call each)
python3 -I scripts/kb/ftcscout.py <team> <year> …             # rating JSON
python3 -I scripts/kb/queue_status.py drafted|failed "<note>" <id>…
```
Paths are instance names with their `<n>` suffix, joined by ` / ` (copy them from `tree`). A 403 on fetch means the document isn't public: mark it `failed` and take the next queued id.

**Splitting mechanisms that aren't subassemblies** (user feedback on 18365 BIOBUZZ V1, K17): don't settle for "(inferred)" with no render.
- A subassembly named "Drive Motor Assembly" is only the motor pack. The drivetrain card is the wheels + the parallel side plates (+ bellypan, pods, motor packs).
- Shooter and turret in one subassembly: the turret is the bottom (turret plate, ring bearing, ring gear, encoder); the shooter is everything above.
- Frame plates that sit in another subassembly (e.g. back plates and a grid plate inside "Top Assembly") still belong to the drivetrain.
- "Vector wheels" / "Vectored Wheel" parts are compliant intake wheels, not drive wheels. Front bars of wheels are the intake, even when they share a subassembly with the drivetrain.
- If a subassembly name says turret but nothing rotates (18365 DECODE "Spindexer Turret"), there's no turret card.
- Turret drives seen so far: servo-ganged ring gear (Droid Force, 3 Axon Max), chain wrapped around a turntable (4410), custom printed ring bearing (25070). Wires routed through inner/outer guide rings = "drag-chain turret": say so in `notable`.
- Loose parts: place COTS parts by their occurrence transforms in `assembly.json` (no API call). Rows of wheels at the front are the intake; wheel stacks rising toward the shooter are the transfer. Custom parts usually carry descriptive names (`Transfer Rail`, `Intake Wedge`).
- Renders: `onshape_fetch.py step <id>` (≈6 calls, STEP keeps positions), import into a throwaway Fusion document via `execute_code` (~20 s for 860 bodies), turn off every occurrence except the mechanism (`isLightBulbOn`), set the camera with Z up, `viewport.saveAsImageFile(path, 600, 450)`, then close the document and re-activate the previous one (the close returns "refers to a deleted Object"; ignore it).

Pilot lessons (details in the plan, K12–K16): motor names sit on assembly instances, not parts; look for the team number on the number plate in the render; one shooter + turret subassembly gets one render shared by both cards.

## Limits

- **Onshape API calls are capped per year: 2,500 on the user's plan.** Over the cap, Onshape rejects every call (HTTP 402) until the year resets, and Onshape gives no way to see usage. So:
  - Append every Onshape call that returns 2xx/3xx to **`kb/ingest/api_calls.csv`** (`timestamp, robot_id, endpoint, status`). Only 2xx/3xx count against the cap; 403s and other errors don't.
  - **Hard stop at 2,000 logged calls for the year** (500 kept in reserve). Warn the user when the log passes 1,500.
  - **150 calls per run** unless the user says otherwise.
  - Expected cost: a full robot ≈ 3 + 1 per mechanism (≈ 8); a mechanism-only entry = 3. The whole backlog is ≈ 1,400.
  - Stop cleanly when a budget is reached and report how many robots are left.
- **Batch sizes:** the first run is a **pilot of 10 robots** (BIOBUZZ and DECODE). Stop after the pilot and wait for the user's review. After that, run batches of about 25.
- On a 429 or 5xx from any API, wait and retry once, then mark the robot `failed` and move on.
- Never write to a robot document whose `status` isn't `pending`. Those have been reviewed.

## After review

- `status: "changes"`: read `review.note`, fix the draft, and set `status` back to `"pending"` (pin the write with `if_version`).
- `status: "approved"`: exported into `kb/robots/<id>/` and `kb/ideas.csv` in two steps: (1) `ArtifactData` `list` on `robots` with `out_dir: kb/ingest/drafts/_review`, (2) `python3 -I scripts/kb/export_approved.py`. The export is idempotent and uses the local renders in `kb/ingest/drafts/<id>/draft.json`, so keep those folders until a robot is exported. Run it when the user asks, or after a review round.
- **Mechanism rating:** each mechanism can carry `bias`: `"lower"` (0.85×), `"normal"` or `"higher"` (1.15×). The reviewer sets it on the page or asks for it in a note. The exported mechanism's multiplier is the robot's rating × bias.
- **Removing a mechanism:** when the reviewer says to remove one ("don't even mention the drivetrain"), delete it from `mechanisms` and drop its ideas, rather than marking it dropped.
- **Fully combined robots:** if the whole robot is one assembly with no mechanism subassemblies (everything inferred), say so in the first question. The user rejects these ("it's all combined, not one I want to reference").
- `status: "rejected"`: delete its working files in `kb/ingest/drafts/<id>/` and mark the queue row `rejected`.

## Report at the end of each run

A short message to the user with: robots drafted, failed (with reasons), skipped, API calls used, and anything you noticed that should change this brief (for example a naming pattern that breaks the mechanism split). Add durable lessons to the plan's spike-results table.

## Decided with the user (2026-10-19)
- Non-Onshape entries are skipped now and ingested later through Fusion.
- **All ~150 mechanism-only entries get drafted.** The user reviews them quickly, so keep those drafts short: one mechanism, its facets, 1–3 ideas, and questions only when something matters.
- Budget: 150 calls per run, a hard stop at 2,000 per year (see "Limits").
