"""goBILDA parts: index, name→SKU matching, kb_find_part, STEP cache (no network)."""

import csv
import io
import json
import zipfile

import pytest

from fusion360_mcp import kb_parts
from fusion360_mcp.kb import KnowledgeBase
from fusion360_mcp.kb_tools import call_kb_tool

FIELDS = [
    "sku", "name", "type", "series", "length_mm", "dims", "hole_pattern",
    "mass_g", "price", "counts_as", "product_url", "step_url",
]

# Real catalog names (kb/parts/parts.csv, scraped 2026-10-20).
PARTS = [
    # sku, name, type, length_mm, dims, mass_g, counts_as
    ("1309-0016-4008", "1309 Series Sonic Hub (8mm REX Bore)", "hub", "",
     {"bore": "8mm REX"}, "14", "none"),
    ("5203-2402-0001", "5203 Series Yellow Jacket Motor (1:1 Ratio, 24mm Length "
     "8mm REX Shaft, 6000 RPM, 3.3 - 5V Encoder)", "motor", "",
     {"ratio": "1:1", "rpm": 6000, "shaft": "8mm REX"}, "391", "motor"),
    ("5203-2402-0019", "5203 Series Yellow Jacket Planetary Gear Motor (19.2:1 "
     "Ratio, 24mm Length 8mm REX Shaft, 312 RPM, 3.3 - 5V Encoder)", "motor", "",
     {"ratio": "19.2:1", "rpm": 312}, "425", "motor"),
    ("1120-0001-0048", "1120 Series U-Channel (1 Hole, 48mm Length)", "channel",
     "48", {"holes": 1}, "32", "none"),
    ("1121-0001-0048", "1121 Series Low-Side U-Channel (1 Hole, 48mm Length)",
     "channel", "48", {"holes": 1}, "25", "none"),
    ("1120-0003-0096", "1120 Series U-Channel (3 Hole, 96mm Length)", "channel",
     "96", {"holes": 3}, "61", "none"),
    ("1120-0004-0120", "1120 Series U-Channel (4 Hole, 120mm Length)", "channel",
     "120", {"holes": 4}, "75", "none"),
]


def _write_parts(kb_dir, rows=PARTS):
    path = kb_dir / "parts" / "parts.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for sku, name, ptype, length, dims, mass, counts in rows:
            w.writerow({
                "sku": sku, "name": name, "type": ptype, "series": sku[:4],
                "length_mm": length, "dims": json.dumps(dims), "mass_g": mass,
                "counts_as": counts, "step_url": f"https://x/{sku}.zip",
            })
    return path


@pytest.fixture
def kb(tmp_path, monkeypatch):
    monkeypatch.setenv("FUSION_MCP_STEP_CACHE", str(tmp_path / "step-cache"))
    kb_dir = tmp_path / "kb"
    _write_parts(kb_dir)
    return KnowledgeBase(kb_dir)


def _skus(parts):
    return [p["sku"] for p in parts]


# ── name → SKU ───────────────────────────────────────────────────────


def _rows():
    return [{"sku": p[0], "name": p[1], "norm": kb_parts.norm_text(p[1])}
            for p in PARTS]


@pytest.mark.parametrize(
    "cad_name, sku",
    [
        # Onshape FTC-library names (vendor suffix "(GB)")
        ("Sonic Hub - 8mm  REX  (GB)", "1309-0016-4008"),
        ("6000rpm Motor - Bare (GB)", "5203-2402-0001"),
        ("1 Hole U-Channel (GB)", "1120-0001-0048"),
        # Full catalog names with the SKU, or just the SKU plus a revision
        ("5203 Series Yellow Jacket Planetary Gear Motor (19.2:1 Ratio, 24mm "
         "Length 8mm REX Shaft, 312 RPM, 3.3 - 5V Encoder) 5203-2402-0019",
         "5203-2402-0019"),
        ("1120-0003-0096 v1 (2)", "1120-0003-0096"),
        ("1150 rpm 5203-2402-0001", "5203-2402-0001"),
    ],
)
def test_cad_names_resolve_to_skus(cad_name, sku):
    assert kb_parts.match_sku(cad_name, _rows()) == sku


def test_numbers_must_match_exactly():
    rows = _rows()
    assert kb_parts.match_sku("2 Hole U-Channel (GB)", rows) is None
    assert kb_parts.match_sku("5000rpm Motor - Bare (GB)", rows) is None
    # A SKU not in the catalog falls back to the name, never to a near SKU.
    assert kb_parts.match_sku("1120-0003-0097", rows) is None


def test_normalize_splits_numbers_from_words():
    nums, words = kb_parts.normalize("8x14x5mm Bearing - Round Bore (GB)")
    assert nums == {"8mm", "14mm", "5mm"}
    assert words == {"bearing", "round"}
    nums, _ = kb_parts.normalize("20t Slip Fit Gear (24 Tooth) Gusset (2-1) M4")
    assert nums == {"20t", "24t", "2-1", "m4"}


# ── index + filters ──────────────────────────────────────────────────


def test_parts_are_indexed_separately_from_docs(kb):
    assert kb.stats() == {}
    assert len(kb.find_parts(limit=50)) == len(PARTS)


def test_exact_filters(kb):
    assert _skus(kb.find_parts(counts_as="motor")) == [
        "5203-2402-0001", "5203-2402-0019"]
    assert _skus(kb.find_parts(type="channel", series="1121")) == ["1121-0001-0048"]
    assert _skus(kb.find_parts(sku="1309-0016-4008")) == ["1309-0016-4008"]


def test_length_is_exact_unless_a_tolerance_is_given(kb):
    assert kb.find_parts(type="channel", length_mm=100) == []
    assert _skus(kb.find_parts(type="channel", length_mm=96)) == ["1120-0003-0096"]
    near = kb.find_parts(type="channel", length_mm=100, length_tol_mm=25)
    assert _skus(near) == ["1120-0003-0096", "1120-0004-0120"]


def test_name_search_ranks_closest_name_first(kb):
    hits = kb.find_parts(name="u-channel 48mm")
    assert _skus(hits)[0] == "1120-0001-0048"
    assert set(_skus(hits)) == {"1120-0001-0048", "1121-0001-0048"}


def test_parts_reindex_when_csv_changes(kb):
    assert kb.find_parts(sku="9999-0000-0001") == []
    _write_parts(kb.kb_dir, PARTS + [("9999-0000-0001", "Test Part", "other", "",
                                      {}, "", "none")])
    assert _skus(kb.find_parts(sku="9999-0000-0001")) == ["9999-0000-0001"]


# ── tool ─────────────────────────────────────────────────────────────


def test_kb_find_part_one_line_per_part(kb):
    result = call_kb_tool("kb_find_part", {"name": "Sonic Hub - 8mm REX (GB)"}, kb)
    assert not result.isError
    assert result.content[0].text == (
        "1309-0016-4008 · 1309 Series Sonic Hub (8mm REX Bore) · hub · "
        "bore=8mm REX · 14g · STEP not cached (download=true)"
    )


def test_kb_find_part_needs_a_filter_and_explains_no_match(kb):
    assert call_kb_tool("kb_find_part", {}, kb).isError
    text = call_kb_tool("kb_find_part", {"type": "gear"}, kb).content[0].text
    assert text.startswith("No parts match")


def test_motor_line_says_it_counts_as_a_motor(kb):
    text = call_kb_tool("kb_find_part", {"sku": "5203-2402-0019"}, kb).content[0].text
    assert "ratio=19.2:1, rpm=312" in text
    assert "counts as motor" in text


# ── STEP cache ───────────────────────────────────────────────────────

STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n"


def _zip(**files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_download_unzips_once_and_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("FUSION_MCP_STEP_CACHE", str(tmp_path / "c"))
    calls = []

    def opener(url):
        calls.append(url)
        return _zip(**{"readme.txt": b"x", "1309-0016-4008.STEP": STEP})

    path = kb_parts.download_step("1309-0016-4008", "https://x/a.zip", opener)
    assert path == tmp_path / "c" / "1309-0016-4008.step"
    assert path.read_bytes() == STEP
    assert kb_parts.download_step("1309-0016-4008", "https://x/a.zip", opener) == path
    assert len(calls) == 1


def test_download_rejects_non_step_and_missing_url(tmp_path, monkeypatch):
    monkeypatch.setenv("FUSION_MCP_STEP_CACHE", str(tmp_path / "c"))
    with pytest.raises(ValueError, match="no STEP file listed"):
        kb_parts.download_step("1309-0016-4008", "")
    with pytest.raises(ValueError, match="did not return a STEP"):
        kb_parts.download_step("1309-0016-4008", "u", lambda u: b"<html>")
    with pytest.raises(ValueError, match="no .step"):
        kb_parts.download_step("1309-0016-4008", "u", lambda u: _zip(a=b"x"))
    with pytest.raises(ValueError, match="Bad SKU"):
        kb_parts.cached_step("../etc/passwd")


def test_kb_find_part_download(kb, monkeypatch):
    monkeypatch.setattr(
        kb_parts.urllib.request, "urlopen",
        lambda req, timeout: io.BytesIO(_zip(**{"p.step": STEP})),
    )
    args = {"sku": "1309-0016-4008", "download": True}
    result = call_kb_tool("kb_find_part", args, kb)
    assert not result.isError
    path = kb_parts.cached_step("1309-0016-4008")
    assert result.content[0].text.endswith(f"STEP file: {path}")
    line = call_kb_tool("kb_find_part", {"sku": "1309-0016-4008"}, kb).content[0].text
    assert line.endswith(f"STEP cached: {path}")
    many = call_kb_tool("kb_find_part", {"type": "channel", "download": True}, kb)
    assert many.isError and "exactly 1 match" in many.content[0].text
