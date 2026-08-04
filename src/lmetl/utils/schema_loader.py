"""Load schema definitions from YAML config and generate JSON Schema / Pydantic models."""

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, Field, create_model


# YAML type string → (python_type, json_schema_type, is_optional, is_list)
_TYPE_MAP: Dict[str, Tuple[type, str, bool, bool]] = {
    "str": (str, "string", False, False),
    "str?": (str, "string", True, False),
    "int": (int, "integer", False, False),
    "int?": (int, "integer", True, False),
    "float": (float, "number", False, False),
    "float?": (float, "number", True, False),
    "list[str]": (str, "string", False, True),
}


def _parse_type(type_str: str) -> Tuple[type, str, bool, bool]:
    """Parse YAML type string into (base_type, json_type, is_optional, is_list)."""
    if type_str in _TYPE_MAP:
        return _TYPE_MAP[type_str]
    raise ValueError(f"Unknown YAML type: {type_str!r}. Supported: {list(_TYPE_MAP.keys())}")


def _reject_nested_list_object(field: Dict[str, Any]) -> None:
    """list[object] nests scalars and list[str] only (depth-1)."""
    for nested in field.get("fields", []):
        if nested.get("type") == "list[object]":
            raise ValueError(
                f"list[object] field {field['name']!r} nests another list[object] "
                f"({nested['name']!r}) — depth-1 only"
            )


def _scalar_prop(
    type_str: str, description: str, constraints: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool]:
    """JSON Schema property for a scalar/list[str] field; returns (prop, is_required)."""
    base_type, json_type, is_optional, is_list = _parse_type(type_str)

    if is_list:
        prop: Dict[str, Any] = {
            "type": "array",
            "items": {"type": json_type},
            "description": description,
        }
        required = False
    elif is_optional:
        prop = {"type": [json_type, "null"], "description": description}
        required = False
    else:
        prop = {"type": json_type, "description": description}
        required = True

    for key in ("ge", "le", "gt", "lt"):
        if key in constraints:
            json_key = {"ge": "minimum", "le": "maximum", "gt": "exclusiveMinimum", "lt": "exclusiveMaximum"}[key]
            prop[json_key] = constraints[key]
    if "default" in constraints:
        prop["default"] = constraints["default"]

    return prop, required


class SchemaLoader:
    """Reads schema definitions from lmetl YAML config."""

    def __init__(self, config: Dict[str, Any]):
        """Accept the lmetl config dict (the value under 'lmetl' key)."""
        self._schemas = config.get("schemas", {})
        self._extraction = config.get("extraction", {})

    def get_fields(self, section: str) -> List[Dict[str, Any]]:
        """Return field definitions for 'core' or a genre name."""
        if section == "core":
            core_def = self._schemas.get("core", {})
            return core_def.get("fields", [])

        genres = self._schemas.get("genres", {})
        genre_def = genres.get(section, {})
        return genre_def.get("fields", [])

    def get_system_prompt_suffix(self, genre: str) -> str:
        """Return genre's system_prompt_suffix."""
        genres = self._schemas.get("genres", {})
        genre_def = genres.get(genre, {})
        return genre_def.get("system_prompt_suffix", "")

    def build_json_schema(self, core: bool = True, genre: Optional[str] = None) -> Dict[str, Any]:
        """Merge core + genre fields into a JSON Schema dict."""
        properties: Dict[str, Any] = {}
        required: List[str] = []

        fields: List[Dict[str, Any]] = []
        if core:
            fields.extend(self.get_fields("core"))
        if genre:
            fields.extend(self.get_fields(genre))

        for field in fields:
            name = field["name"]
            type_str = field.get("type", "str?")
            description = field.get("description", "")
            constraints = field.get("constraints", {})

            if type_str == "list[object]":
                properties[name] = self._object_array_prop(field)
                continue

            prop, is_required = _scalar_prop(type_str, description, constraints)
            if is_required:
                required.append(name)
            properties[name] = prop

        schema: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required

        return schema

    @staticmethod
    def _object_array_prop(field: Dict[str, Any]) -> Dict[str, Any]:
        """JSON Schema property for a list[object] entity field (depth-1)."""
        _reject_nested_list_object(field)
        nested_props: Dict[str, Any] = {}
        nested_required: List[str] = []
        for nested in field.get("fields", []):
            prop, is_required = _scalar_prop(
                nested.get("type", "str?"),
                nested.get("description", ""),
                nested.get("constraints", {}),
            )
            if is_required:
                nested_required.append(nested["name"])
            nested_props[nested["name"]] = prop

        items: Dict[str, Any] = {"type": "object", "properties": nested_props}
        if nested_required:
            items["required"] = nested_required
        return {
            "type": "array",
            "items": items,
            "description": field.get("description", ""),
        }

    @staticmethod
    def _instruction_line(field: Dict[str, Any]) -> str:
        """One '- name: description' instruction line; entity fields list their sub-fields."""
        name = field["name"]
        description = field.get("description", "")
        if field.get("type") != "list[object]":
            return f"- {name}: {description}"
        parts = "、".join(
            f"{nf['name']}={nf.get('description', '')}" for nf in field.get("fields", [])
        )
        return f"- {name}: {description}（物件列表；欄位：{parts}）"

    def build_extraction_instructions(self, core: bool = True, genre: Optional[str] = None) -> str:
        """Build Chinese extraction instruction text from field name + description."""
        lines: List[str] = []

        if core:
            core_fields = self.get_fields("core")
            if core_fields:
                lines.append("### Core（必填）")
                for f in core_fields:
                    lines.append(self._instruction_line(f))

        if genre:
            genre_fields = self.get_fields(genre)
            if genre_fields:
                genre_label = genre.capitalize()
                lines.append(f"### {genre_label} Genre（{genre}領域）")
                for f in genre_fields:
                    lines.append(self._instruction_line(f))

        return "\n".join(lines)

    def build_pydantic_model(self, section: str) -> Type[BaseModel]:
        """Dynamically create a Pydantic model from YAML field definitions."""
        fields = self.get_fields(section)
        if not fields:
            raise ValueError(f"No fields found for section: {section!r}")

        model_fields: Dict[str, Any] = {}

        for field in fields:
            name = field["name"]
            type_str = field.get("type", "str?")
            description = field.get("description", "")
            constraints = field.get("constraints", {})

            if type_str == "list[object]":
                item_model = self._build_item_model(section, field)
                model_fields[name] = (
                    List[item_model],  # type: ignore[valid-type]
                    Field(default_factory=list, description=description),
                )
                continue

            base_type, _, is_optional, is_list = _parse_type(type_str)

            field_kwargs: Dict[str, Any] = {"description": description}

            # Apply constraints
            for key in ("ge", "le", "gt", "lt"):
                if key in constraints:
                    field_kwargs[key] = constraints[key]

            if is_list:
                annotation = List[base_type]  # type: ignore[valid-type]
                field_kwargs["default_factory"] = list
            elif is_optional:
                annotation = Optional[base_type]  # type: ignore[valid-type]
                field_kwargs["default"] = constraints.get("default", None)
            else:
                annotation = base_type
                if "default" in constraints:
                    field_kwargs["default"] = constraints["default"]

            model_fields[name] = (annotation, Field(**field_kwargs))

        model_name = section.capitalize() + "ExtractionResult"
        return create_model(model_name, **model_fields)

    @staticmethod
    def _build_item_model(section: str, field: Dict[str, Any]) -> Type[BaseModel]:
        """Nested Pydantic model for one list[object] field's items (depth-1)."""
        _reject_nested_list_object(field)
        item_fields: Dict[str, Any] = {}
        for nested in field.get("fields", []):
            base_type, _, is_optional, is_list = _parse_type(nested.get("type", "str?"))
            kwargs: Dict[str, Any] = {"description": nested.get("description", "")}
            if is_list:
                annotation: Any = List[base_type]  # type: ignore[valid-type]
                kwargs["default_factory"] = list
            elif is_optional:
                annotation = Optional[base_type]  # type: ignore[valid-type]
                kwargs["default"] = None
            else:
                annotation = base_type
            item_fields[nested["name"]] = (annotation, Field(**kwargs))

        item_name = section.capitalize() + field["name"].capitalize() + "Item"
        return create_model(item_name, **item_fields)
