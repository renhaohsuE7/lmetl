"""Tests for SchemaLoader — YAML-driven schema handling."""

import pytest

from lmetl.utils.schema_loader import SchemaLoader, _parse_type


# Minimal config for testing
_TEST_CONFIG = {
    "schemas": {
        "core": {
            "system_prompt_suffix": "",
            "fields": [
                {"name": "title", "type": "str?", "description": "文件標題"},
                {"name": "authors", "type": "list[str]", "description": "作者列表"},
                {"name": "year", "type": "int?", "description": "年度"},
                {"name": "confidence_score", "type": "float", "description": "信心分數",
                 "constraints": {"ge": 0.0, "le": 1.0, "default": 0.0}},
            ],
        },
        "genres": {
            "geology": {
                "system_prompt_suffix": "你具備地質學專業知識。",
                "fields": [
                    {"name": "rock_types", "type": "list[str]", "description": "岩石類型"},
                    {"name": "geological_age", "type": "str?", "description": "地質年代"},
                ],
            },
        },
    },
    "extraction": {"core": True, "genre": "geology"},
}


class TestParseType:
    def test_str(self):
        base, json_type, opt, lst = _parse_type("str")
        assert base is str
        assert json_type == "string"
        assert not opt
        assert not lst

    def test_str_optional(self):
        base, json_type, opt, lst = _parse_type("str?")
        assert opt is True
        assert not lst

    def test_int_optional(self):
        base, json_type, opt, lst = _parse_type("int?")
        assert base is int
        assert json_type == "integer"
        assert opt is True

    def test_float(self):
        base, json_type, opt, lst = _parse_type("float")
        assert base is float
        assert json_type == "number"
        assert not opt

    def test_list_str(self):
        base, json_type, opt, lst = _parse_type("list[str]")
        assert base is str
        assert lst is True

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown YAML type"):
            _parse_type("dict[str, int]")


class TestSchemaLoader:
    def test_get_core_fields(self):
        loader = SchemaLoader(_TEST_CONFIG)
        fields = loader.get_fields("core")
        assert len(fields) == 4
        names = [f["name"] for f in fields]
        assert "title" in names
        assert "confidence_score" in names

    def test_get_genre_fields(self):
        loader = SchemaLoader(_TEST_CONFIG)
        fields = loader.get_fields("geology")
        assert len(fields) == 2
        assert fields[0]["name"] == "rock_types"

    def test_get_nonexistent_section(self):
        loader = SchemaLoader(_TEST_CONFIG)
        fields = loader.get_fields("medical")
        assert fields == []

    def test_get_system_prompt_suffix(self):
        loader = SchemaLoader(_TEST_CONFIG)
        suffix = loader.get_system_prompt_suffix("geology")
        assert "地質學" in suffix

    def test_build_json_schema_core_only(self):
        loader = SchemaLoader(_TEST_CONFIG)
        schema = loader.build_json_schema(core=True, genre=None)
        assert schema["type"] == "object"
        props = schema["properties"]
        assert "title" in props
        assert props["title"]["type"] == ["string", "null"]  # str? → optional
        assert "authors" in props
        assert props["authors"]["type"] == "array"  # list[str]
        # confidence_score is required (non-optional float)
        assert "confidence_score" in schema.get("required", [])

    def test_build_json_schema_with_genre(self):
        loader = SchemaLoader(_TEST_CONFIG)
        schema = loader.build_json_schema(core=True, genre="geology")
        props = schema["properties"]
        assert "title" in props
        assert "rock_types" in props
        assert "geological_age" in props

    def test_build_json_schema_constraints(self):
        loader = SchemaLoader(_TEST_CONFIG)
        schema = loader.build_json_schema(core=True, genre=None)
        cs = schema["properties"]["confidence_score"]
        assert cs["minimum"] == 0.0
        assert cs["maximum"] == 1.0
        assert cs["default"] == 0.0

    def test_build_extraction_instructions(self):
        loader = SchemaLoader(_TEST_CONFIG)
        instructions = loader.build_extraction_instructions(core=True, genre="geology")
        assert "### Core" in instructions
        assert "- title: 文件標題" in instructions
        assert "### Geology Genre" in instructions
        assert "- rock_types: 岩石類型" in instructions

    def test_build_pydantic_model_core(self):
        loader = SchemaLoader(_TEST_CONFIG)
        Model = loader.build_pydantic_model("core")
        assert Model.__name__ == "CoreExtractionResult"

        # Validate with data
        instance = Model(title="test", authors=["A"], year=2024, confidence_score=0.9)
        assert instance.title == "test"
        assert instance.confidence_score == 0.9

    def test_build_pydantic_model_genre(self):
        loader = SchemaLoader(_TEST_CONFIG)
        Model = loader.build_pydantic_model("geology")
        assert Model.__name__ == "GeologyExtractionResult"

        instance = Model(rock_types=["安山岩"], geological_age="更新世")
        assert instance.rock_types == ["安山岩"]

    def test_build_pydantic_model_defaults(self):
        loader = SchemaLoader(_TEST_CONFIG)
        Model = loader.build_pydantic_model("core")

        # All optional/list fields should have defaults
        instance = Model()
        assert instance.title is None
        assert instance.authors == []
        assert instance.year is None
        assert instance.confidence_score == 0.0

    def test_build_pydantic_model_validation(self):
        loader = SchemaLoader(_TEST_CONFIG)
        Model = loader.build_pydantic_model("core")

        # confidence_score has ge=0.0, le=1.0
        with pytest.raises(Exception):
            Model(confidence_score=2.0)

    def test_build_pydantic_model_nonexistent_raises(self):
        loader = SchemaLoader(_TEST_CONFIG)
        with pytest.raises(ValueError, match="No fields found"):
            loader.build_pydantic_model("nonexistent")
