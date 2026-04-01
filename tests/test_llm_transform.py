"""Tests for YAML-driven PromptBuilder."""

from lmetl.llm.prompts import PromptBuilder


def _make_config(core=True, genre=None):
    """Build a minimal lmetl config dict for testing."""
    config = {
        "extraction": {"core": core, "genre": genre},
        "prompts": {
            "version": "1.0",
            "system": (
                "你是一位專業的文獻分析師，負責從研究報告中萃取結構化資訊。\n"
                "請根據提供的文件段落，萃取所要求的欄位。\n"
                "回覆必須是合法的 JSON 格式，符合指定的 schema。\n"
                "如果某個欄位在文件中找不到相關資訊，請設為 null 或空陣列。\n"
                "請附上 confidence_score (0.0-1.0) 表示你對萃取結果的信心程度。\n"
                "請附上 thinking 欄位，簡述你的推理過程。\n"
            ),
            "user_template": (
                "## 文件：{source_file}\n"
                "## 章節：{source_section}\n\n"
                "## 內容：\n{content}\n\n"
                "## 萃取要求：\n{extraction_instructions}\n\n"
                "## JSON Schema：\n```json\n{json_schema}\n```\n\n"
                "請以合法 JSON 回覆，不要加入任何其他文字。\n"
            ),
        },
        "schemas": {
            "core": {
                "system_prompt_suffix": "",
                "fields": [
                    {"name": "title", "type": "str?", "description": "文件標題"},
                    {"name": "authors", "type": "list[str]", "description": "作者列表"},
                    {"name": "confidence_score", "type": "float", "description": "信心分數 (0.0-1.0)",
                     "constraints": {"ge": 0.0, "le": 1.0, "default": 0.0}},
                    {"name": "thinking", "type": "str?", "description": "推理過程"},
                ],
            },
            "genres": {
                "geology": {
                    "system_prompt_suffix": (
                        "你同時具備地質學與地熱能源專業知識，"
                        "能辨識岩性、地層、溫度梯度、鑽井資訊等專業術語。"
                    ),
                    "fields": [
                        {"name": "rock_types", "type": "list[str]", "description": "岩石類型"},
                        {"name": "formations", "type": "list[str]", "description": "地層名稱"},
                    ],
                },
            },
        },
    }
    return config


class TestPromptBuilder:
    def test_system_prompt_core_only(self):
        config = _make_config(core=True, genre=None)
        builder = PromptBuilder(config)
        prompt = builder.build_system_prompt()
        assert "文獻分析師" in prompt
        assert "地質" not in prompt

    def test_system_prompt_with_geology(self):
        config = _make_config(core=True, genre="geology")
        builder = PromptBuilder(config)
        prompt = builder.build_system_prompt()
        assert "地質" in prompt

    def test_user_prompt_contains_content(self):
        config = _make_config(core=True, genre="geology")
        builder = PromptBuilder(config)
        chunk = {
            "source_file": "test.docx",
            "source_section": "第一章",
            "content": "地熱探勘資料分析",
        }
        prompt = builder.build_user_prompt(chunk)
        assert "test.docx" in prompt
        assert "第一章" in prompt
        assert "地熱探勘資料分析" in prompt
        assert "Core" in prompt
        assert "Geology" in prompt

    def test_json_schema_core(self):
        config = _make_config(core=True, genre=None)
        builder = PromptBuilder(config)
        schema = builder.get_json_schema()
        assert "properties" in schema
        assert "title" in schema["properties"]

    def test_json_schema_with_geology(self):
        config = _make_config(core=True, genre="geology")
        builder = PromptBuilder(config)
        schema = builder.get_json_schema()
        props = schema.get("properties", {})
        assert "title" in props
        assert "rock_types" in props
