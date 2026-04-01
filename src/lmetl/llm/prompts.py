"""Prompt builder — YAML-driven, no hardcoded prompts."""

import json
from typing import Any, Dict, Optional

from lmetl.utils.schema_loader import SchemaLoader


class PromptBuilder:
    """Builds system and user prompts entirely from YAML config."""

    def __init__(self, config: Dict[str, Any]):
        """Accept the lmetl config dict (the value under 'lmetl' key).

        Args:
            config: The lmetl section from pipeline YAML.
        """
        self.schema_loader = SchemaLoader(config)
        self.prompts_config = config.get("prompts", {})
        self.extraction_config = config.get("extraction", {})

    @property
    def core(self) -> bool:
        return self.extraction_config.get("core", True)

    @property
    def genre(self) -> Optional[str]:
        return self.extraction_config.get("genre")

    def build_system_prompt(self) -> str:
        base = self.prompts_config.get("system", "").rstrip()
        genre = self.genre
        if genre:
            suffix = self.schema_loader.get_system_prompt_suffix(genre).rstrip()
            if suffix:
                base += "\n" + suffix
        return base

    def build_user_prompt(self, chunk: Dict[str, Any]) -> str:
        template = self.prompts_config.get("user_template", "")

        instructions = self.schema_loader.build_extraction_instructions(
            core=self.core, genre=self.genre
        )
        json_schema = self.schema_loader.build_json_schema(
            core=self.core, genre=self.genre
        )

        return template.format(
            source_file=chunk.get("source_file", "unknown"),
            source_section=chunk.get("source_section", ""),
            content=chunk.get("content", ""),
            extraction_instructions=instructions,
            json_schema=json.dumps(json_schema, ensure_ascii=False, indent=2),
        )

    def get_json_schema(self) -> Dict[str, Any]:
        return self.schema_loader.build_json_schema(
            core=self.core, genre=self.genre
        )
