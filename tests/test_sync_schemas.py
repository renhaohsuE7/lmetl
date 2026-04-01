"""Tests for sync_schemas CLI tool."""

import subprocess
import sys

from lmetl.tools.sync_schemas import generate_model_code, sync_schemas


class TestGenerateModelCode:
    def test_generates_valid_python(self):
        fields = [
            {"name": "title", "type": "str?", "description": "文件標題"},
            {"name": "authors", "type": "list[str]", "description": "作者列表"},
            {"name": "score", "type": "float", "description": "分數",
             "constraints": {"ge": 0.0, "le": 1.0, "default": 0.0}},
        ]
        code = generate_model_code("TestModel", "Test docstring.", fields)

        assert "class TestModel(BaseModel):" in code
        assert "from pydantic import BaseModel, Field" in code
        assert "title: Optional[str]" in code
        assert "authors: List[str]" in code
        assert "score: float" in code
        assert "ge=0.0" in code
        assert "le=1.0" in code

        # Should be valid Python
        compile(code, "<test>", "exec")

    def test_imports_only_needed(self):
        fields = [{"name": "name", "type": "str?", "description": "名稱"}]
        code = generate_model_code("OnlyOptional", "Test.", fields)
        assert "Optional" in code
        assert "List" not in code

    def test_list_only_imports(self):
        fields = [{"name": "items", "type": "list[str]", "description": "項目"}]
        code = generate_model_code("OnlyList", "Test.", fields)
        assert "List" in code
        assert "Optional" not in code


class TestSyncSchemas:
    def test_check_mode_passes(self):
        """After generating, check mode should pass."""
        # First generate
        sync_schemas("configs/base.yaml", check_only=False)
        # Then check — should return True
        result = sync_schemas("configs/base.yaml", check_only=True)
        assert result is True

    def test_cli_check_mode(self):
        """Test CLI --check mode via subprocess."""
        # Ensure files are generated first
        subprocess.run(
            [sys.executable, "-m", "lmetl.tools.sync_schemas", "configs/base.yaml"],
            check=True,
        )
        # Check should pass
        result = subprocess.run(
            [sys.executable, "-m", "lmetl.tools.sync_schemas", "--check", "configs/base.yaml"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "OK" in result.stdout
