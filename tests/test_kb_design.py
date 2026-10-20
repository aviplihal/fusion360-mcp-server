"""Robot design file, kb_save_design, session resources and prompts (no Fusion)."""

import json
import shutil
from pathlib import Path

import pytest

from fusion360_mcp import kb_design as kd
from fusion360_mcp.kb import KnowledgeBase, parse_frontmatter
from fusion360_mcp.kb_tools import call_kb_tool

REPO_KB = Path(__file__).resolve().parents[1] / "kb"
CONSTRAINTS = {
    "season": "2026-27",
    "game": "BIOBUZZ",
    "manual_version": "TU05",
    "starting_size": {"box": [45.7, 45.7, 45.7]},
    "expansion_size": {"box": [45.7, 61.0, 73.65]},
    "actuators": {"max_motors": {"count": 8}, "max_servos": {"count": 8}},
    "scoring_elements": {"POLLEN": {"diameter_cm": 7.1}},
}


@pytest.fixture
def kb_dir(tmp_path):
    d = tmp_path / "kb"
    (d / "rules" / "2026-27").mkdir(parents=True)
    (d / "rules" / "2026-27" / "constraints.json").write_text(json.dumps(CONSTRAINTS))
    (d / "designs" / "_template").mkdir(parents=True)
    shutil.copy(
        REPO_KB / "designs" / "_template" / "design.md", d / "designs/_template"
    )
    shutil.copy(REPO_KB / "design_rules.md", d)
    shutil.copy(REPO_KB / "lessons.md", d)
    kd.create_design(d, "BB1")
    return d


def box(x0, y0, z0, x1, y1, z1):
    return {"min": [x0, y0, z0], "max": [x1, y1, z1]}


def specs(kb_dir, robot="bb1"):
    path = kd.design_path(kb_dir, robot)
    return kd.parse_design(path.read_text().splitlines())


# ── design file ──────────────────────────────────────────────────────


def test_create_from_template_drops_the_format_comment(kb_dir):
    text = kd.design_path(kb_dir, "bb1").read_text()
    assert text.startswith("# Robot design: BB1")
    assert "season 2026-27 BIOBUZZ" in text
    assert "{date}" not in text and "<!--" not in text
    assert list(specs(kb_dir)) == [
        "drivetrain",
        "intake",
        "transfer",
        "shooter",
        "turret",
    ]
    assert specs(kb_dir)["shooter"]["status"] == "not started"
    with pytest.raises(ValueError, match="already exists"):
        kd.create_design(kb_dir, "bb1")


def test_update_subsystem_merges_fields_and_logs(kb_dir):
    budget, warnings = kd.update_subsystem(
        kb_dir,
        "bb1",
        "shooter",
        {
            "status": "concept",
            "motors": 2,
            "envelope": box(-10, -5, 15, 10, 15, 40),
            "interfaces": [
                {"name": "base plate", "where": "z=15", "provided_by": "drivetrain"}
            ],
        },
    )
    assert budget == "Budget: motors 2/8, servos 0/8"
    assert warnings == []
    s = specs(kb_dir)["shooter"]
    assert s["status"] == "concept" and s["component"] == "Shooter"
    assert s["interfaces"][0]["provided_by"] == "drivetrain"
    text = kd.design_path(kb_dir, "bb1").read_text()
    assert "shooter: status 'not started'→'concept', motors 0→2, envelope" in text
    # The human notes under the spec line survive.
    assert text.count("Notes:") == 5


def test_budget_over_eight_is_refused_and_not_written(kb_dir):
    kd.update_subsystem(kb_dir, "bb1", "drivetrain", {"motors": 4})
    kd.update_subsystem(kb_dir, "bb1", "shooter", {"motors": 3})
    before = kd.design_path(kb_dir, "bb1").read_text()
    with pytest.raises(ValueError, match="Motors total 9 > 8"):
        kd.update_subsystem(kb_dir, "bb1", "intake", {"motors": 2})
    with pytest.raises(ValueError, match="Servos total 9 > 8"):
        kd.update_subsystem(kb_dir, "bb1", "turret", {"servos": 9})
    assert kd.design_path(kb_dir, "bb1").read_text() == before


def test_envelope_must_fit_the_start_cube(kb_dir):
    with pytest.raises(ValueError, match="leaves the starting cube"):
        kd.update_subsystem(
            kb_dir, "bb1", "intake", {"envelope": box(-20, 15, 0, 20, 30, 10)}
        )
    with pytest.raises(ValueError, match="min must be smaller"):
        kd.update_subsystem(
            kb_dir, "bb1", "intake", {"envelope": box(0, 0, 0, 0, 1, 1)}
        )


def test_extended_box_is_checked_against_the_expansion_limit(kb_dir):
    stowed = box(-20, 10, 0, 20, 22.85, 10)
    kd.update_subsystem(
        kb_dir,
        "bb1",
        "intake",
        {"envelope": stowed, "extended": box(-20, 10, 0, 20, 38, 10)},
    )
    with pytest.raises(ValueError, match="expansion limit"):
        kd.update_subsystem(
            kb_dir, "bb1", "intake", {"extended": box(-20, 10, 0, 20, 38, 80)}
        )


def test_new_subsystem_goes_before_open_questions(kb_dir):
    kd.update_subsystem(kb_dir, "bb1", "Hang Hook", {"servos": 1})
    lines = kd.design_path(kb_dir, "bb1").read_text().splitlines()
    assert lines.index("## Subsystem: hang-hook") < lines.index("## Open questions")
    assert specs(kb_dir)["hang-hook"]["component"] == "HangHook"


def test_overlapping_envelopes_warn(kb_dir):
    kd.update_subsystem(
        kb_dir, "bb1", "shooter", {"envelope": box(-10, -10, 10, 10, 10, 40)}
    )
    _, warnings = kd.update_subsystem(
        kb_dir, "bb1", "turret", {"envelope": box(-12, -12, 8, 12, 12, 20)}
    )
    assert warnings == ["Envelopes of shooter and turret overlap (fine if intended)."]


def test_bad_fields_are_refused(kb_dir):
    with pytest.raises(ValueError, match="status must be"):
        kd.update_subsystem(kb_dir, "bb1", "shooter", {"status": "done"})
    with pytest.raises(ValueError, match="interfaces"):
        kd.update_subsystem(kb_dir, "bb1", "shooter", {"interfaces": ["holes"]})
    with pytest.raises(ValueError, match="Nothing to update"):
        kd.update_subsystem(kb_dir, "bb1", "shooter", {"colour": "red"})


def test_notes_add_and_resolve(kb_dir):
    kd.add_note(kb_dir, "bb1", "Transfer hands balls to the shooter at z = 30 cm?")
    kd.add_note(kb_dir, "bb1", "Wired the shooter", section="log")
    text = kd.design_path(kb_dir, "bb1").read_text()
    lines = text.splitlines()
    q = lines.index("- [ ] Transfer hands balls to the shooter at z = 30 cm?")
    assert lines.index("## Open questions") < q < lines.index("## Change log")
    assert lines[-1].endswith("Wired the shooter")
    line = kd.resolve_note(kb_dir, "bb1", "z = 30", "yes, 31 cm")
    assert line.startswith("- [x] Transfer") and line.endswith("→ yes, 31 cm")
    with pytest.raises(ValueError, match="0 open questions"):
        kd.resolve_note(kb_dir, "bb1", "z = 30")


def test_missing_design_file_says_how_to_create(kb_dir):
    with pytest.raises(FileNotFoundError, match="action=create"):
        kd.get_design(kb_dir, "nope")


def test_hand_edited_bad_spec_is_reported(kb_dir):
    path = kd.design_path(kb_dir, "bb1")
    path.write_text(
        path.read_text().replace(
            'spec: {"status": "not started", "component": "Intake"',
            'spec: {"status": oops',
            1,
        )
    )
    with pytest.raises(ValueError, match="Bad spec line in 'intake'"):
        kd.get_design(kb_dir, "bb1")


# ── robot_design tool ────────────────────────────────────────────────


def test_robot_design_tool_round_trip(kb_dir):
    kb = KnowledgeBase(kb_dir)
    r = call_kb_tool("robot_design", {"action": "create", "robot": "bb2"}, kb)
    assert not r.isError and "Created kb/designs/bb2/design.md" in r.content[0].text
    r = call_kb_tool(
        "robot_design",
        {
            "action": "update_subsystem",
            "robot": "bb2",
            "subsystem": "drivetrain",
            "motors": 4,
            "status": "built",
        },
        kb,
    )
    assert r.content[0].text.startswith("Updated drivetrain. Budget: motors 4/8")
    assert "warning: drivetrain: built but has no envelope." in r.content[0].text
    text = (
        call_kb_tool("robot_design", {"action": "get", "robot": "bb2"}, kb)
        .content[0]
        .text
    )
    assert text.splitlines()[:2] == [
        "kb/designs/bb2/design.md",
        "Budget: motors 4/8, servos 0/8",
    ]
    r = call_kb_tool(
        "robot_design",
        {
            "action": "update_subsystem",
            "robot": "bb2",
            "subsystem": "intake",
            "motors": 5,
        },
        kb,
    )
    assert r.isError and "Motors total 9 > 8" in r.content[0].text
    r = call_kb_tool("robot_design", {"action": "fly", "robot": "bb2"}, kb)
    assert r.isError


# ── kb_save_design ───────────────────────────────────────────────────


def _accept_shooter(kb_dir):
    kd.update_subsystem(
        kb_dir,
        "bb1",
        "shooter",
        {"status": "accepted", "motors": 2, "servos": 1, "based_on": ["cb-x/shooter"]},
    )


SHOOTER_CARD = {
    "robot": "bb1",
    "subsystem": "shooter",
    "name": "Counter roller shooter",
    "facets": {
        "shooter_type": "counter roller",
        "wheel_diameter_mm": 72,
        "hood": "adjustable",
    },
    "notable": "Laser-cut aluminum side plates; FDM hood on a servo.",
    "materials": ["aluminum", "PETG"],
    "decisions": "Counter roller for backspin control.",
}


def test_save_design_refuses_until_accepted(kb_dir):
    with pytest.raises(ValueError, match="Save only accepted"):
        kd.save_design_card(kb_dir, "bb1", "shooter", SHOOTER_CARD)
    with pytest.raises(ValueError, match="not in the design file"):
        kd.save_design_card(kb_dir, "bb1", "arm", SHOOTER_CARD)


def test_save_design_writes_cards_the_index_parses(kb_dir):
    _accept_shooter(kb_dir)
    kb = KnowledgeBase(kb_dir)
    r = call_kb_tool("kb_save_design", SHOOTER_CARD, kb)
    assert not r.isError, r.content[0].text
    assert "Saved ours-bb1/shooter" in r.content[0].text
    meta, body = parse_frontmatter((kb_dir / "robots/ours-bb1/shooter.md").read_text())
    assert meta["rating"] == {"basis": "ours", "multiplier": 1.0}
    assert meta["source"]["site"] == "ours"
    assert (meta["motors"], meta["servos"], meta["path"]) == (2, 1, "Shooter")
    assert meta["based_on"] == ["cb-x/shooter"]
    assert meta["season"] == "2026-27 BIOBUZZ"
    assert "## Decisions and why" in body
    doc = kb.get("ours-bb1/shooter")
    assert doc["kind"] == "mechanism" and doc["ours"] == 1
    robot = kb.get("ours-bb1")
    assert robot["kind"] == "robot" and robot["meta"]["source"] == {
        "site": "ours",
        "design": "kb/designs/bb1/design.md",
    }
    assert [c["id"] for c in robot["children"]] == ["ours-bb1/shooter"]
    hits = kb.search(kind="mechanism", type="shooter", facets={"hood": "adjustable"})
    assert hits[0]["id"] == "ours-bb1/shooter"


def test_saving_a_second_subsystem_updates_the_robot_card(kb_dir):
    _accept_shooter(kb_dir)
    kd.save_design_card(kb_dir, "bb1", "shooter", SHOOTER_CARD)
    kd.update_subsystem(
        kb_dir, "bb1", "drivetrain", {"status": "accepted", "motors": 4}
    )
    kd.save_design_card(
        kb_dir,
        "bb1",
        "drivetrain",
        {"facets": {"drive_type": "mecanum"}, "notable": "Wood prototype frame."},
    )
    kd.save_design_card(kb_dir, "bb1", "shooter", SHOOTER_CARD)
    meta, body = parse_frontmatter((kb_dir / "robots/ours-bb1/robot.md").read_text())
    assert meta["mechanisms"] == ["drivetrain", "shooter"]
    assert body.strip() == "Our own design. Accepted subsystems: drivetrain, shooter."


def test_save_design_enforces_caps_and_facets(kb_dir):
    _accept_shooter(kb_dir)

    def save(**changes):
        return kd.save_design_card(
            kb_dir, "bb1", "shooter", {**SHOOTER_CARD, **changes}
        )

    with pytest.raises(ValueError, match="81 words; the cap is 80"):
        save(notable="word " * 81)
    with pytest.raises(ValueError, match="Unknown shooter facet 'colour'"):
        save(facets={"colour": "red"})
    with pytest.raises(ValueError, match="hood must be one of"):
        save(facets={"hood": "big"})
    with pytest.raises(ValueError, match="notable is required"):
        save(notable=" ")
    with pytest.raises(ValueError, match="cap is 100"):
        save(brief="w " * 101)
    with pytest.raises(ValueError, match="no facets yet"):
        save(type="arm", facets={"x": 1})
    with pytest.raises(ValueError, match="Give type"):
        save(type="blaster")


def test_facet_table_matches_the_search_tool_types():
    from fusion360_mcp.kb_tools import MECHANISM_TYPES

    assert set(kd.FACETS) | set(kd.GENERIC_TYPES) == set(MECHANISM_TYPES)


# ── resources and prompts ────────────────────────────────────────────


def test_resources_serve_files_and_constraints(kb_dir):
    assert set(kd.RESOURCES) == {
        "kb://design-rules",
        "kb://lessons",
        "kb://constraints",
    }
    assert kd.read_kb_resource("kb://design-rules", kb_dir).startswith("# Design rules")
    assert kd.read_kb_resource("kb://lessons", kb_dir).startswith("# Lessons")
    assert (
        json.loads(kd.read_kb_resource("kb://constraints", kb_dir))["game"] == "BIOBUZZ"
    )
    (kb_dir / "lessons.md").unlink()
    assert "not written yet" in kd.read_kb_resource("kb://lessons", kb_dir)
    with pytest.raises(ValueError):
        kd.read_kb_resource("kb://nope", kb_dir)


def test_repo_session_files_follow_the_rules():
    rules = (REPO_KB / "design_rules.md").read_text()
    assert "## Questions for the team" in rules
    rows = [
        ln
        for ln in rules.splitlines()
        if ln.startswith("| ")
        and ln.count("|") == 4
        and not ln.startswith(("| Feature", "| Item"))
    ]
    assert rows and all("unverified — confirm with the team" in ln for ln in rows)
    assert len((REPO_KB / "lessons.md").read_text().splitlines()) <= 150


def test_work_on_subsystem_prompt_inlines_the_context(kb_dir):
    kd.update_subsystem(kb_dir, "bb1", "shooter", {"motors": 2, "status": "concept"})
    text = kd.subsystem_prompt(kb_dir, "bb1", "shooter")
    assert text.startswith("Subsystem session: shooter of robot bb1. Now: concept")
    for needle in (
        'component "Shooter"',
        "kb_search kind=mechanism type=shooter",
        "8 Save:",
        "## Design file (design.md)",
        "## Game constraints",
        "≤ 8 motors and ≤ 8 servos",
        "## Design rules",
        "## Lessons",
        "Never use execute_code",
    ):
        assert needle in text
    assert len(text) < 20000


def test_prompts_without_a_design_file_say_create_it(kb_dir):
    text = kd.subsystem_prompt(kb_dir, "newbot", "intake")
    assert "robot_design action=create" in text
    with pytest.raises(ValueError):
        kd.subsystem_prompt(kb_dir, "newbot", "")


def test_build_whole_robot_orders_drivetrain_first(kb_dir):
    kd.update_subsystem(kb_dir, "bb1", "intake", {"status": "accepted"})
    text = kd.whole_robot_prompt(kb_dir, "bb1")
    assert "Order: drivetrain, transfer, shooter, turret" in text
    assert "P5 list_joints" in text and "## Lessons" in text


def test_hand_written_heading_case_still_matches(kb_dir):
    path = kd.design_path(kb_dir, "bb1")
    path.write_text(
        path.read_text().replace("## Subsystem: shooter", "## Subsystem: Shooter")
    )
    kd.update_subsystem(kb_dir, "bb1", "shooter", {"motors": 1})
    assert specs(kb_dir)["shooter"]["motors"] == 1
    assert path.read_text().count("Subsystem: ") == 5
