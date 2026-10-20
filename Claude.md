Goal: Make a memory base + MCP server that allows claude to completely CAD a FTC robot with human guidance on design.

Upkeep:
1. Do not change this that do not need to be changed for the task you are working on.
2. Follow the 80/20 rule. Look at what will get you 80% while only haveing to do 20% of the work. Ignore if you are requested to optimize
3. Do not leave things half finished. Update the Status.md with the part that you worked on and what needs to be completed next.
4. before doing a large change make a plan. If possible do spike tests that will allow you to test seprate parts before fully commiting this plays into 80/20.
5. When making a large change make a git branch so you dont mess up what is running.
6. When removeing code fully remove it dont commit it out.
7. When you learn something that can be helpfull to a future seasion add it to the learned lessons section.

Parts to the Project:
1. MCP server
    1. Allow the agent to interface with Fusion 360. Keep it simple while giveing the agent as much functionality as possible and keep it fast dont slow down calls because that componds over long sesions.
2. RAG Data base
    1. The data base is what makes this project powerfull it allows seasions to seach: past chats, robot desings, lessons learned about the MCP, design tricks. This should be keep as small as possible and fast to searc while useing as little tokens as possible.

File Structure:
Flow: Claude ←stdio MCP→ src/fusion360_mcp (this server) ←TCP localhost:9876, newline JSON→ addon/ (runs inside Fusion) ←CustomEvent→ Fusion main thread.
All Fusion units are centimeters. Tool names must match add-in command names exactly (forwarded 1:1).

```
fusion360-mcp-server/
├── Claude.md                  # This file: goals, upkeep rules, structure, learned lessons
├── .claude/CLAUDE.md          # Dev notes: architecture, commands, "adding a new command" checklist
├── AGENTS.md                  # Agent-facing tool catalog (all 110 tools grouped by category)
├── README.md                  # Install + user docs
├── pyproject.toml / uv.lock   # Package config (uv). Entry point: fusion360-mcp-server
├── .github/workflows/ci.yml   # CI: pytest + ruff
│
├── src/fusion360_mcp/         # MCP SERVER (Python package, runs outside Fusion)
│   ├── server.py              # Entry point (click CLI, --mode live|mock), MCP resources/prompts, _send routing
│   ├── tools.py               # TOOLS list: 110 tool defs (name, description, inputSchema) + annotation sets
│   ├── connection.py          # TCP client to the add-in (FUSION_MCP_PORT env var overrides 9876)
│   ├── mock.py                # Mock handler for every tool (used by --mode mock and tests)
│   ├── hints.py               # Error classification table — MIRROR of addon/server/hints.py
│   ├── __init__.py / __main__.py  # Package + `python -m fusion360_mcp`
│
├── addon/                     # FUSION ADD-IN (copied/symlinked into Fusion's AddIns folder; can't import src/)
│   ├── Fusion360MCP.py        # Add-in run/stop: registers CustomEvent, starts socket server
│   ├── Fusion360MCP.manifest  # Fusion add-in manifest
│   └── server/
│       ├── command_handler.py # ALL Fusion API logic — one method per tool (~3.8k lines, the big one)
│       ├── socket_server.py   # TCP server on :9876, thread per client
│       ├── event_bridge.py    # Queue + CustomEvent to run work on Fusion's main thread
│       ├── hints.py           # Canonical error-classification table (keep in sync with src copy)
│       ├── hole_geometry.py   # Pure-Python face picking/plane math for create_hole (no adsk)
│       ├── parameter_units.py # Unit handling for user parameters (no adsk)
│       ├── occurrence_refs.py # Occurrence lookup, face/edge refs, bbox union (no adsk)
│       └── __init__.py        # Logging setup (~/fusion360mcp.log, rotating)
│
├── tests/                     # pytest, no Fusion needed
│   ├── test_tools.py          # Tool registry: expected tool-name set, schemas, annotations
│   ├── test_mock.py           # Mock handler per tool
│   ├── test_server.py         # Server routing, resources, prompts, errors
│   ├── test_connection.py     # TCP client
│   ├── test_feedback.py       # Hints, deltas, render_view, formatting
│   ├── test_addon_sync.py     # Drift guard: addon vs src mirrors (hints.py etc.)
│   ├── test_addon_api_usage.py# AST guard: add-in doesn't call nonexistent Fusion APIs
│   ├── test_hole_geometry.py  # create_hole geometry
│   └── test_parameter_units.py# Parameter units
│
├── scripts/
│   ├── install-addon.sh       # Symlinks addon/ into Fusion's AddIns folder (macOS/Windows)
│   └── smoke_envelope.py      # Mock-mode smoke test of response envelopes
│
└── devcontainer/              # Run the server in a Docker devcontainer with Fusion on the Windows host
    ├── README.md
    ├── fusion-mcp-wrapper.sh  # In-container wrapper: TCP relay + launches server
    └── fusion-mcp-bridge.ps1  # Windows host: port proxy + firewall rule
```

Adding a tool touches: addon/server/command_handler.py → src/fusion360_mcp/tools.py → src/fusion360_mcp/mock.py → tests/test_tools.py + tests/test_mock.py (full checklist in .claude/CLAUDE.md).
Dev commands: `uv sync --dev`, `uv run pytest -v`, `uv run ruff check`.
Not built yet: RAG database. Status: Status.md. Plans: docs/plans/.



Learned Lessons:
1. Onshape robot CAD: the BOM "Part number" field is empty. Identify COTS parts by their library names with vendor suffixes ("(GB)", "(REV)", "(SC)"). Subassemblies linked from private documents return 403 on render, so fall back to the whole-robot render. Details: docs/plans/knowledge-base.md (K1–K5).
2. FTC CAD Base has no API, but the home page embeds its whole catalog as JSON in the `self.__next_f.push` strings. Decode those instead of scraping the HTML. Local setup: add-in is symlinked into Fusion's AddIns folder (scripts/install-addon.sh); MCP server is registered at user scope as `fusion360` running from this repo (`uv run --directory <repo> fusion360-mcp-server --mode socket`). New MCP registrations only load after restarting Claude Code.
2. Raw socket test without MCP: `printf '{"type":"ping","params":{}}\n' | nc -w 3 localhost 9876` — the key is "type", not "command". Add-in log: ~/fusion360mcp.log.
3. Spike safely: inside execute_code, do `doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)`, run the test in try/finally, then `doc.close(False)` and `prev.activate()`. The user's open documents are never touched. Pipe JSON from a python script into nc to avoid shell-quoting problems.
4. Parametric designs: `occurrence.transform2` moves the part only temporarily. `design.snapshots.add()` and `computeAll()` both reset it to identity. To get a lasting position, place the part at insert time (`occurrences.addExistingComponent(comp, matrix)`) or use joints. In direct designs, transform2 sticks.
5. `rootComponent.boundingBox` is stale or ignores occurrences. Take the union of `occ.bRepBodies.item(i).boundingBox` instead (body proxies are already in assembly coordinates). `occ.boundingBox` returned 0..0.
6. A face's `entityToken` is about 388 characters, too many tokens to list per hole. Refs like `Occ:1/b0/f37` (body and face index through occ.bRepBodies) are short and resolve to proxies.
7. Pattern features accept occurrences. Moves (moveFeatures) don't. STEP import via `importManager.importToTarget2` returns an ObjectCollection of occurrences; the component comes in named "(Unsaved) (n)" with a timestamp partNumber, so rename it.
8. Live-test handler changes without restarting the add-in: inside execute_code, `importlib.reload` the add-in's `server.command_handler` (find it in sys.modules), make a fresh `CommandHandler()`, and call `h.execute_command({...})` in a throwaway document. The running add-in keeps the old code until it is restarted.
9. Joints: the first occurrence moves to the second, so it can't be the grounded part. `JointGeometry.createByPoint` takes only a point (use `point.createForAssemblyContext(occ)`). Interference results are temporary bodies with no assembly context.
10. Lasting placement in parametric designs: re-insert (`addExistingComponent(comp, matrix)`, then `old.deleteMe()`). It survives computeAll but renumbers the occurrence (Plate:1 -> Plate:2). The `SnapshotCmd` UI command doesn't capture from the API. In direct designs, `addExistingComponent` composes the matrix with the first occurrence's transform, so set `transform2` afterwards. `isGrounded` can't be read on sub-component occurrences.
11. Joints between copies of one component fail silently ("conflicts with assembly relationships"; the joint is created with a timeline warning and nothing moves) until `isGroundToParent = False` is set on the occurrences. Always check `joint.timelineObject.healthState`. Direct designs don't move parts for joints at all.
12. Hole keypoints: `JointGeometry.createByNonPlanarFace(face, Start/EndKeyPoint).origin` gives the hole's two ends in assembly coordinates. Moving part `end` → fixed `start` stacks the mover on the fixed hole's start side; `start` → `end` on the end side. The `undo` command inside one execute call doesn't remove a just-added joint.
13. Joint values: `jointMotion.rotationValue`/`slideValue` last only until the next recompute (`computeAll` or any new feature). Editing a limit resets the value to 0, and values outside the limits are silently ignored. For a lasting value, set `joint.angle`/`joint.offset`. `isFlipped` can't be edited on an existing joint, so delete the joint and re-add it. `root.allJoints` is a vector with no `.item()`, so iterate it.
14. Timeline: a collapsed group is one item with healthState 5 (unknown), so read its children instead. Health states: 0 healthy, 1 warning, 2 error, 3 suppressed, 4 rolled back. Fusion names joints with a space ("Revolute 1").
15. Features on a component's body land in that component whether built through `root.features` with proxies or `comp.features` with native entities. Use native, so planes and coordinates are component-local. `importToTarget2(opts, parent_comp)` already returns the occurrence as a proxy in the parent's context.
16. Parallel agents: `isolation: worktree` branched from `main`, not the current branch, so tell agents to reset to the intended commit first. Other sessions' big STEP imports block Fusion for 20–75 s, so retry on a timeout. Never `git checkout -- uv.lock` in the main checkout: it holds the user's uncommitted change.
17. NEVER clean up by looping over `app.documents` and closing the ones "not in the list from before": comparing Document objects (`==` or `in`) isn't reliable, and on 2026-10-20 that loop closed all of the user's documents without saving. Keep a list of the exact Document objects the test created (`app.activeDocument` right after each new/open) and close only those, after checking `isValid`.
11. Robot ingest: Onshape documents that are only link-shared (`public: false`) return 403 on the assembly even though `GET /documents` works, so expect ~40% of CAD Base links to fail. Motor and servo names sit on assembly instances, not parts. Scripts and the run steps are in docs/plans/robot-ingest-brief.md ("Tools").
13. Parallel sessions share one Fusion: only one may drive it at a time. Big STEP imports block Fusion's main thread for up to ~75 s and can drop the MCP socket, so they must never overlap with another session's live tests. Name the current Fusion user at the top of Status.md.
14. goBILDA's robots.txt asks AI agents for a 10 s crawl delay; the product data is embedded as JSON in the category pages, so scrape those (cached) instead of product pages. `uv run --frozen` stops uv from rewriting uv.lock.
