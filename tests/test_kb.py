"""Knowledge base index, search and MCP tools (no Fusion needed)."""

import json
import os
import time

import pytest

from fusion360_mcp.kb import KnowledgeBase, fts_query, parse_frontmatter
from fusion360_mcp.kb_tools import KB_TOOLS, call_kb_tool, get_kb_tool_list, is_kb_tool
from fusion360_mcp.tools import TOOLS


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _robot(kb_dir, robot_id, title, multiplier, season, mechanisms):
    rating = json.dumps(
        {"basis": "ftcscout", "multiplier": multiplier, "detail": "test"}
    )
    _write(
        kb_dir / "robots" / robot_id / "robot.md",
        f"---\nid: {robot_id}\ntitle: {title}\nseason: {season}\n"
        f'team: {{"number": 1234, "name": "Test Team"}}\nrating: {rating}\n---\n\n'
        f"{title} summary.\n",
    )
    for key, (mtype, name, facets, notable) in mechanisms.items():
        _write(
            kb_dir / "robots" / robot_id / f"{key}.md",
            f"---\ntype: {mtype}\nname: {name}\nfacets: {json.dumps(facets)}\n"
            f"rating: {rating}\nseason: {season}\n---\n\n{notable}\n",
        )


@pytest.fixture
def kb_dir(tmp_path):
    d = tmp_path / "kb"
    _write(d / "rules" / "2026-27" / "constraints.json", "{}")
    _write(
        d / "books" / "manual" / "rules" / "R503.md",
        "---\nid: R503\n"
        "title: ROBOTS are limited to a total of 8 motors and 8 servos.\n"
        "page: 134\n---\n\nROBOTS are limited to a total of 8 motors and 8 servos.\n",
    )
    _write(
        d / "books" / "manual" / "sections" / "9.1.md",
        "---\nid: 9.1\ntitle: Overview\npage: 63\n---\n\nThe field overview.\n",
    )
    _write(
        d / "books" / "manual" / "sections" / "9.10.md",
        "---\nid: 9.10\ntitle: AprilTags\npage: 76\n---\n\nAprilTag targets.\n",
    )
    _robot(
        d,
        "cb-strong",
        "Strong Bot",
        1.25,
        "2026-27 BIOBUZZ",
        {
            "shooter": (
                "shooter",
                "Counter roller shooter",
                {
                    "shooter_type": "counter roller",
                    "wheel_diameter_mm": 72,
                    "hood": "adjustable",
                },
                "One motor drives the flywheel and counter roller.",
            ),
            "drivetrain": (
                "drivetrain",
                "Mecanum base",
                {"drive_type": "mecanum"},
                "Bare motors at 12:1.",
            ),
        },
    )
    _robot(
        d,
        "cb-weak",
        "Weak Bot",
        0.85,
        "2025-26 DECODE",
        {
            "shooter": (
                "shooter",
                "Flywheel shooter",
                {"shooter_type": "single flywheel", "wheel_diameter_mm": 96},
                "Single flywheel with a fixed hood and counter roller idea.",
            ),
        },
    )
    _write(
        d / "ideas.csv",
        "id,mechanism,text,tags,seen_in,source\n"
        "i1,shooter,Power flywheel and counter roller from one motor.,belts,"
        "cb-strong;cb-weak;cb-x,robots\n"
        "i2,shooter,Use a heavy flywheel mass for consistent shots.,,cb-weak,robots\n",
    )
    return d


@pytest.fixture
def kb(kb_dir):
    return KnowledgeBase(kb_dir)


# ── parsing ──────────────────────────────────────────────────────────


def test_frontmatter_keeps_ids_as_text_and_parses_json():
    meta, body = parse_frontmatter(
        '---\nid: 9.10\npage: 76\nfacets: {"a": 1}\nmechanisms: [x, y]\n---\nBody\n'
    )
    assert meta == {
        "id": "9.10",
        "page": 76,
        "facets": {"a": 1},
        "mechanisms": ["x", "y"],
    }
    assert body == "Body\n"


def test_fts_query_expands_synonyms_and_prefixes():
    q = fts_query("launcher hood")
    for term in ('"shooter"*', '"flywheel"*', '"launcher"*', '"hood"*'):
        assert term in q
    assert fts_query("") == ""
    assert fts_query("!!") == ""


# ── index and search ─────────────────────────────────────────────────


def test_indexes_every_kind(kb):
    assert kb.stats() == {"book": 2, "idea": 2, "mechanism": 3, "rule": 1, "robot": 2}


def test_section_ids_that_look_like_numbers_do_not_collide(kb):
    assert kb.get("manual/9.10")["title"] == "AprilTags"
    assert kb.get("manual/9.1")["title"] == "Overview"


def test_search_finds_rule(kb):
    assert kb.search("how many motors and servos")[0]["id"] == "R503"
    assert [h["id"] for h in kb.search("motors", kind="rule")] == ["R503"]


def test_filters_kind_type_and_exact_facets(kb):
    hits = kb.search(
        kind="mechanism", type="shooter", facets={"shooter_type": "counter roller"}
    )
    assert [h["id"] for h in hits] == ["cb-strong/shooter"]
    hits = kb.search(kind="mechanism", facets={"wheel_diameter_mm": 96})
    assert [h["id"] for h in hits] == ["cb-weak/shooter"]


def test_stronger_team_ranks_first(kb):
    hits = kb.search("counter roller", kind="mechanism")
    assert [h["id"] for h in hits][:2] == ["cb-strong/shooter", "cb-weak/shooter"]


def test_filter_only_search_orders_by_rating(kb):
    hits = kb.search(kind="robot")
    assert [h["id"] for h in hits] == ["cb-strong", "cb-weak"]


def test_ideas_rank_by_how_often_seen(kb):
    hits = kb.search("flywheel", kind="idea")
    assert [h["id"] for h in hits] == ["i1", "i2"]


def test_season_filter(kb):
    assert {h["id"] for h in kb.search(kind="robot", season="DECODE")} == {"cb-weak"}


def test_get_robot_lists_its_mechanisms(kb):
    doc = kb.get("CB-STRONG")
    assert doc["kind"] == "robot"
    assert [c["id"] for c in doc["children"]] == [
        "cb-strong/drivetrain",
        "cb-strong/shooter",
    ]


def test_reindexes_when_a_file_changes(kb, kb_dir):
    assert not kb.search("turret")
    path = kb_dir / "books" / "manual" / "rules" / "R503.md"
    path.write_text(path.read_text() + "\nA turret counts too.\n")
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert kb.search("turret")[0]["id"] == "R503"


def test_bad_facet_name_is_rejected(kb):
    with pytest.raises(ValueError):
        kb.search(facets={"x') OR 1=1 --": 1})


def test_missing_folder_explains_the_env_var(tmp_path):
    with pytest.raises(FileNotFoundError, match="FUSION_MCP_KB_DIR"):
        KnowledgeBase(tmp_path / "nope").stats()


# ── MCP tools ────────────────────────────────────────────────────────


def test_kb_tools_are_separate_from_fusion_tools():
    names = {t["name"] for t in KB_TOOLS}
    assert names == {"kb_search", "kb_get"}
    assert not names & {t["name"] for t in TOOLS}
    assert all(is_kb_tool(n) for n in names)
    assert not is_kb_tool("extrude")
    for tool in get_kb_tool_list():
        assert tool.annotations.readOnlyHint is True


def test_kb_search_tool_returns_one_line_per_hit(kb):
    result = call_kb_tool(
        "kb_search", {"query": "counter roller", "kind": "mechanism"}, kb
    )
    lines = result.content[0].text.splitlines()
    assert not result.isError
    assert lines[0].startswith("cb-strong/shooter · shooter · Counter roller shooter")
    assert lines[0].endswith("1.25×")


def test_kb_get_tool_formats_robot(kb):
    text = call_kb_tool("kb_get", {"id": "cb-strong"}, kb).content[0].text
    assert "rating: 1.25× test" in text
    assert "Mechanisms (open with kb_get):" in text
    assert "cb-strong/shooter · shooter" in text


def test_kb_get_unknown_id_suggests(kb):
    result = call_kb_tool("kb_get", {"id": "R50"}, kb)
    assert result.isError
    assert "R503" in result.content[0].text


def test_kb_search_no_matches(kb):
    result = call_kb_tool("kb_search", {"query": "zzzz"}, kb)
    assert result.content[0].text.startswith("No matches")


def test_reindexes_when_index_version_changes(kb, kb_dir, monkeypatch):
    kb.stats()
    fresh = KnowledgeBase(kb_dir)
    monkeypatch.setattr("fusion360_mcp.kb.INDEX_VERSION", "test-bump")
    rebuilt = []
    original = fresh._rebuild
    monkeypatch.setattr(fresh, "_rebuild", lambda *a: rebuilt.append(1) or original(*a))
    assert fresh.stats()["rule"] == 1
    assert rebuilt == [1]


def test_snippets_stay_on_one_line():
    from fusion360_mcp.kb_tools import hit_line

    doc = {
        "id": "R1",
        "kind": "rule",
        "title": "T",
        "type": None,
        "meta": {},
        "multiplier": 1.0,
        "snip": "first\nA. second",
    }
    assert hit_line(doc) == "R1 · rule · T\n    first A. second"


def test_robot_card_stays_a_robot_for_mechanism_only_entries(kb_dir):
    _write(
        kb_dir / "robots" / "cb-mech" / "robot.md",
        "---\nid: cb-mech\ntitle: Just a drivetrain\nkind: mechanism\n"
        "entry: mechanism\n---\n\nOne drivetrain.\n",
    )
    doc = KnowledgeBase(kb_dir).get("cb-mech")
    assert doc["kind"] == "robot"
    assert doc["meta"]["entry"] == "mechanism"


def test_hit_line_shows_key_facets_first_and_labels_numbers():
    from fusion360_mcp.kb_tools import hit_line

    doc = {
        "id": "r/shooter",
        "kind": "mechanism",
        "type": "shooter",
        "title": "Shooter",
        "multiplier": 1.0,
        "snip": None,
        "meta": {
            "facets": {
                "feeder": "kicker",
                "game_piece": "other",
                "hood": "adjustable",
                "shooter_type": "counter roller",
                "wheel_diameter_mm": 72,
            }
        },
    }
    assert hit_line(doc) == (
        "r/shooter · shooter · Shooter · "
        "counter roller, wheel_diameter_mm=72, adjustable"
    )


def test_kb_get_shows_team_and_source_compactly(kb):
    text = call_kb_tool("kb_get", {"id": "cb-strong"}, kb).content[0].text
    assert "team: 1234 Test Team" in text
    assert "{'number'" not in text
