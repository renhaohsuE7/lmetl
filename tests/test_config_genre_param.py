"""Per-request genre loading (audit finding ④b, 2026-08-04).

load_lmetl_config previously loaded ONLY the genre named inside base.yaml;
callers (the wrapper) then overrode extraction.genre WITHOUT the new genre's
YAML ever being read — a request for an existing non-default genre silently
degraded to core-only extraction. The genre must be applied BEFORE the
genre-file autoload.
"""

import textwrap

from lmetl.utils.config import load_lmetl_config


def _write_config_tree(tmp_path):
    (tmp_path / "genres").mkdir()
    (tmp_path / "base.yaml").write_text(textwrap.dedent("""\
        lmetl:
          extraction:
            core: true
            genre: geologytest
          schemas:
            core:
              fields:
                - name: title
                  type: str?
                  description: t
    """))
    (tmp_path / "genres" / "geologytest.yaml").write_text(textwrap.dedent("""\
        fields:
          - name: rock_types
            type: list[str]
            description: r
    """))
    (tmp_path / "genres" / "wellstest.yaml").write_text(textwrap.dedent("""\
        fields:
          - name: wells_field
            type: list[str]
            description: w
    """))
    return str(tmp_path / "base.yaml")


def test_default_genre_loads_from_base_yaml(tmp_path):
    config = load_lmetl_config(_write_config_tree(tmp_path))
    assert "geologytest" in config["schemas"]["genres"]


def test_genre_param_loads_that_genres_yaml(tmp_path):
    config = load_lmetl_config(_write_config_tree(tmp_path), genre="wellstest")
    assert config["extraction"]["genre"] == "wellstest"
    assert "wellstest" in config["schemas"]["genres"], (
        "requesting a non-default genre must load its YAML (④b: previously "
        "only base.yaml's own genre was ever loaded)"
    )
    fields = config["schemas"]["genres"]["wellstest"]["fields"]
    assert fields[0]["name"] == "wells_field"


def test_genre_param_unknown_stays_core_only(tmp_path):
    # "base" (and any genre without a YAML) keeps the load-bearing silent
    # core-only behavior — the gateway's default LMETL_GENRE is "base".
    config = load_lmetl_config(_write_config_tree(tmp_path), genre="base")
    assert config["extraction"]["genre"] == "base"
    assert "base" not in config["schemas"].get("genres", {})
