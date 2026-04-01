"""Configuration helpers for lmetl."""

import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml

_ENV_PATTERN = re.compile(r"\$\{(\w+):([^}]*)\}")


def _resolve_env_vars(obj: Any) -> Any:
    """Resolve ${VAR:default} patterns in config values."""
    if isinstance(obj, str):
        def _replace(m: re.Match) -> str:
            return os.environ.get(m.group(1), m.group(2))
        return _ENV_PATTERN.sub(_replace, obj)
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars(v) for v in obj]
    return obj


def load_lmetl_config(config_path: str) -> Dict[str, Any]:
    """Load the lmetl-specific section from a pipeline YAML config."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        full_config = yaml.safe_load(f)

    return _resolve_env_vars(full_config.get("lmetl", {}))
