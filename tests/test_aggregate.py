"""AllInfoAccumulator — document-level all_info master table (design: lamp §9e).

Rule-based, zero LLM calls. Keys mirror the genre schema; per-chunk extractions
merge in as they complete. Incremental fill == one final merge pass (pure rules);
chunk order is document order, so first-wins rules are deterministic by design.
"""

import pytest

from lmetl.aggregate import AllInfoAccumulator, normalize_identity

FIELDS = [
    {"name": "title", "type": "str?", "description": "文件標題"},
    {"name": "year", "type": "int?", "description": "年度"},
    {"name": "key_findings", "type": "list[str]", "description": "關鍵發現"},
    {"name": "report_no", "type": "str?", "merge": "collect", "description": "報告編號"},
    {"name": "confidence_score", "type": "float", "description": "信心分數"},
    {"name": "thinking", "type": "str?", "description": "推理"},
    {"name": "llm_commentary", "type": "str?", "description": "評析"},
    {
        "name": "wells",
        "type": "list[object]",
        "identity": "name",
        "description": "鑽井/溫泉井資訊",
        "fields": [
            {"name": "name", "type": "str", "description": "井名"},
            {"name": "depth", "type": "str?", "description": "深度"},
            {"name": "temperature", "type": "str?", "description": "溫度"},
            {"name": "aliases", "type": "list[str]", "description": "別名"},
        ],
    },
]


def acc():
    return AllInfoAccumulator(FIELDS)


class TestNormalizeIdentity:
    def test_fullwidth_whitespace_case(self):
        # NFKC folds full-width; whitespace removed entirely; case folded.
        assert normalize_identity("ＴＨ－１") == normalize_identity("th-1")
        assert normalize_identity("泰安 公井") == normalize_identity("泰安公井")
        assert normalize_identity("  TH-1　") == normalize_identity("TH-1")


class TestListStr:
    def test_union_dedupe_preserves_first_appearance_order(self):
        a = acc()
        a.add_chunk("c1", {"key_findings": ["A", "B"]})
        a.add_chunk("c2", {"key_findings": ["B", "C"]})
        r = a.result()
        assert r["key_findings"] == ["A", "B", "C"]
        assert r["_provenance"]["key_findings"] == {
            "A": ["c1"], "B": ["c1", "c2"], "C": ["c2"],
        }

    def test_bare_string_coerced_to_single_item(self):
        a = acc()
        a.add_chunk("c1", {"key_findings": "單一發現"})
        assert a.result()["key_findings"] == ["單一發現"]


class TestScalar:
    def test_first_non_null_and_same_value_accumulates_provenance(self):
        a = acc()
        a.add_chunk("c1", {"title": None})
        a.add_chunk("c2", {"title": "T1"})
        a.add_chunk("c3", {"title": "T2"})  # differing later value: dropped
        a.add_chunk("c4", {"title": "T1"})  # same value re-seen: provenance grows
        r = a.result()
        assert r["title"] == "T1"
        assert r["_provenance"]["title"] == ["c2", "c4"]

    def test_empty_string_does_not_claim_first_non_null(self):
        a = acc()
        a.add_chunk("c1", {"title": ""})
        a.add_chunk("c2", {"title": "真標題"})
        assert a.result()["title"] == "真標題"

    def test_int_zero_is_a_value_not_absence(self):
        a = acc()
        a.add_chunk("c1", {"year": 0})
        a.add_chunk("c2", {"year": 2020})
        assert a.result()["year"] == 0

    def test_collect_strategy(self):
        a = acc()
        a.add_chunk("c1", {"report_no": "R-1"})
        a.add_chunk("c2", {"report_no": "R-2"})
        a.add_chunk("c3", {"report_no": "R-1"})
        assert a.result()["report_no"] == [
            {"value": "R-1", "source_chunk_ids": ["c1", "c3"]},
            {"value": "R-2", "source_chunk_ids": ["c2"]},
        ]


class TestEntityMerge:
    def test_fill_missing_fields_across_chunks(self):
        a = acc()
        a.add_chunk("c1", {"wells": [{"name": "TH-1", "depth": "1200m"}]})
        a.add_chunk("c2", {"wells": [{"name": "TH-1", "temperature": "180℃"}]})
        wells = a.result()["wells"]
        assert len(wells) == 1
        w = wells[0]
        assert w["name"] == "TH-1"
        assert w["depth"] == "1200m"
        assert w["temperature"] == "180℃"
        assert w["source_chunk_ids"] == ["c1", "c2"]
        assert w["conflicts"] == []

    def test_conflict_keeps_first_and_records(self):
        a = acc()
        a.add_chunk("c1", {"wells": [{"name": "TH-1", "depth": "1200m"}]})
        a.add_chunk("c2", {"wells": [{"name": "TH-1", "depth": "1500m"}]})
        w = a.result()["wells"][0]
        assert w["depth"] == "1200m"
        assert w["conflicts"] == [{"field": "depth", "value": "1500m", "chunk_id": "c2"}]

    def test_same_value_after_normalization_is_not_a_conflict(self):
        a = acc()
        a.add_chunk("c1", {"wells": [{"name": "TH-1", "depth": "1200m"}]})
        a.add_chunk("c2", {"wells": [{"name": "TH-1", "depth": "1200 m"}]})
        w = a.result()["wells"][0]
        assert w["depth"] == "1200m"  # first-seen raw form kept
        assert w["conflicts"] == []
        assert w["source_chunk_ids"] == ["c1", "c2"]

    def test_identity_normalization_merges_variants(self):
        a = acc()
        a.add_chunk("c1", {"wells": [{"name": "TH-1", "depth": "1200m"}]})
        a.add_chunk("c2", {"wells": [{"name": "ＴＨ－１", "temperature": "180℃"}]})
        a.add_chunk("c3", {"wells": [{"name": "泰安 公井"}, {"name": "泰安公井", "depth": "150m"}]})
        wells = a.result()["wells"]
        assert len(wells) == 2
        th1 = wells[0]
        assert th1["name"] == "TH-1"  # display name = first-seen raw
        assert th1["depth"] == "1200m"
        assert th1["temperature"] == "180℃"
        taian = wells[1]
        assert taian["name"] == "泰安 公井"
        assert taian["depth"] == "150m"

    def test_missing_identity_appends_anonymous_no_merge(self):
        a = acc()
        a.add_chunk("c1", {"wells": [{"depth": "60m"}]})
        a.add_chunk("c2", {"wells": [{"name": "", "depth": "60m"}]})
        wells = a.result()["wells"]
        assert len(wells) == 2  # anonymous entities never merge
        assert all(w["source_chunk_ids"] for w in wells)

    def test_nested_list_str_unions(self):
        a = acc()
        a.add_chunk("c1", {"wells": [{"name": "TH-1", "aliases": ["虎山井"]}]})
        a.add_chunk("c2", {"wells": [{"name": "TH-1", "aliases": ["虎山井", "一號井"]}]})
        assert a.result()["wells"][0]["aliases"] == ["虎山井", "一號井"]

    def test_unknown_nested_keys_ignored(self):
        a = acc()
        a.add_chunk("c1", {"wells": [{"name": "TH-1", "bogus": "x"}]})
        assert "bogus" not in a.result()["wells"][0]


class TestExclusionsAndStats:
    def test_llm_fields_excluded_confidence_becomes_stats(self):
        a = acc()
        a.add_chunk("c1", {"thinking": "…", "llm_commentary": "…", "confidence_score": 0.9})
        a.add_chunk("c2", {"confidence_score": 0.7})
        r = a.result()
        assert "thinking" not in r
        assert "llm_commentary" not in r
        assert "confidence_score" not in r
        assert r["_stats"]["confidence_min"] == 0.7
        assert r["_stats"]["confidence_avg"] == pytest.approx(0.8)

    def test_failed_chunks_counted_not_fatal(self):
        a = acc()
        a.add_chunk("c1", {"title": "T"})
        a.add_failed_chunk("c2")
        r = a.result()
        assert r["title"] == "T"
        assert r["_stats"]["chunks_merged"] == 1
        assert r["_stats"]["chunks_failed"] == 1

    def test_unknown_top_level_keys_ignored(self):
        a = acc()
        a.add_chunk("c1", {"bogus": "x", "title": "T"})
        assert "bogus" not in a.result()


class TestResultShape:
    def test_stable_shape_when_nothing_seen(self):
        r = acc().result()
        assert r["title"] is None
        assert r["year"] is None
        assert r["key_findings"] == []
        assert r["report_no"] == []   # collect field
        assert r["wells"] == []
        assert r["_stats"] == {
            "chunks_merged": 0,
            "chunks_failed": 0,
            "confidence_min": None,
            "confidence_avg": None,
        }
        assert r["_provenance"] == {}

    def test_keys_follow_schema_order(self):
        a = acc()
        a.add_chunk("c1", {"title": "T", "wells": [{"name": "W"}]})
        keys = list(a.result().keys())
        assert keys == ["title", "year", "key_findings", "report_no", "wells",
                        "_provenance", "_stats"]

    def test_deterministic_rerun(self):
        def run():
            a = acc()
            a.add_chunk("c1", {"title": "T", "key_findings": ["A"],
                               "wells": [{"name": "TH-1", "depth": "1200m"}]})
            a.add_chunk("c2", {"wells": [{"name": "TH-1", "temperature": "180℃"}]})
            return a.result()
        assert run() == run()


class TestNestedDepthGuard:
    def test_nested_list_object_rejected(self):
        bad = [{
            "name": "outer", "type": "list[object]", "identity": "name",
            "fields": [{"name": "inner", "type": "list[object]", "fields": []}],
        }]
        with pytest.raises(ValueError):
            AllInfoAccumulator(bad)
