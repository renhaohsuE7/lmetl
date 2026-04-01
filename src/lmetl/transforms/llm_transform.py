"""LLMTransform: send document chunks to LLM for structured extraction."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

import pathway as pw
from pwetl.transforms import BaseTransform

from lmetl.llm.client import LLMClient
from lmetl.llm.prompts import PromptBuilder
from lmetl.utils.config import load_lmetl_config
from lmetl.utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)


class LLMTransform(BaseTransform):
    """Transforms document chunks into structured extraction results via LLM."""

    def setup(self) -> None:
        config_path = os.environ.get("LMETL_CONFIG", "configs/base.yaml")
        self.etl_config = load_lmetl_config(config_path)

        # Config-driven initialization
        self.client = LLMClient(self.etl_config.get("llm", {}))
        self.prompt_builder = PromptBuilder(self.etl_config)

        extraction_config = self.etl_config.get("extraction", {})
        self.schema_version = extraction_config.get("schema_version", "1.0")
        prompts_config = self.etl_config.get("prompts", {})
        self.prompt_version = prompts_config.get("version", "1.0")

        logger.info(
            "LLMTransform setup: endpoint=%s, model=%s, genre=%s",
            self.client.endpoint,
            self.client.model,
            extraction_config.get("genre"),
        )

    def transform(self, tables: Dict[str, pw.Table]) -> Dict[str, pw.Table]:
        # Find the source table (first one available)
        source_name = next(iter(tables))
        chunks_table = tables[source_name]

        client = self.client
        prompt_builder = self.prompt_builder
        schema_version = self.schema_version
        prompt_version = self.prompt_version

        def extract_udf(
            chunk_id: str,
            source_file: str,
            source_page: int,
            source_page_end: int,
            source_section: str,
            source_position: str,
            content: str,
            content_type: str,
            image_refs: str,
            token_estimate: int,
        ) -> str:
            """UDF: call LLM per chunk, return JSON string with result + metadata."""
            chunk_data = {
                "chunk_id": chunk_id,
                "source_file": source_file,
                "source_section": source_section,
                "content": content,
            }

            system_prompt = prompt_builder.build_system_prompt()
            user_prompt = prompt_builder.build_user_prompt(chunk_data)

            try:
                response = client.extract(system_prompt, user_prompt)
                parsed, error = parse_llm_json(response.content)

                if parsed is not None:
                    return json.dumps(
                        {
                            "chunk_id": chunk_id,
                            "source_file": source_file,
                            "source_page": source_page,
                            "source_section": source_section,
                            "source_position": source_position,
                            "is_structured": True,
                            "extraction_result": parsed,
                            "fallback_text": "",
                            "extraction_method": "direct_prompt",
                            "extraction_mode": "metadata_only",
                            "extracted_at": datetime.now(timezone.utc).isoformat(),
                            "latency_ms": response.latency_ms,
                            "model_name": response.model_name,
                            "model_endpoint": response.model_endpoint,
                            "token_usage_input": response.token_usage_input,
                            "token_usage_output": response.token_usage_output,
                            "confidence_score": parsed.get("confidence_score", 0.0),
                            "thinking_content": parsed.get("thinking", ""),
                            "schema_version": schema_version,
                            "prompt_version": prompt_version,
                            "validation_status": "pending",
                        },
                        ensure_ascii=False,
                    )
                else:
                    logger.warning("Failed to parse LLM response for chunk %s: %s", chunk_id, error)
                    return json.dumps(
                        {
                            "chunk_id": chunk_id,
                            "source_file": source_file,
                            "source_page": source_page,
                            "source_section": source_section,
                            "source_position": source_position,
                            "is_structured": False,
                            "extraction_result": {},
                            "fallback_text": (
                                f"LLM response not valid JSON: {error}\n"
                                f"RAW RESPONSE:\n{response.content[:3000]}\n\n"
                                f"ORIGINAL CONTENT:\n{content[:3000]}"
                            ),
                            "extraction_method": "direct_prompt",
                            "extraction_mode": "metadata_only",
                            "extracted_at": datetime.now(timezone.utc).isoformat(),
                            "latency_ms": response.latency_ms,
                            "model_name": response.model_name,
                            "model_endpoint": response.model_endpoint,
                            "token_usage_input": response.token_usage_input,
                            "token_usage_output": response.token_usage_output,
                            "confidence_score": 0.0,
                            "thinking_content": "",
                            "schema_version": schema_version,
                            "prompt_version": prompt_version,
                            "validation_status": "pending",
                        },
                        ensure_ascii=False,
                    )
            except Exception as e:
                logger.error("LLM extraction failed for chunk %s: %s", chunk_id, e)
                return json.dumps(
                    {
                        "chunk_id": chunk_id,
                        "source_file": source_file,
                        "source_page": source_page,
                        "source_section": source_section,
                        "source_position": source_position,
                        "is_structured": False,
                        "extraction_result": {},
                        "fallback_text": (
                            f"EXTRACTION ERROR: {e}\n\n"
                            f"ORIGINAL CONTENT:\n{content[:3000]}"
                        ),
                        "extraction_method": "direct_prompt",
                        "extraction_mode": "metadata_only",
                        "extracted_at": datetime.now(timezone.utc).isoformat(),
                        "latency_ms": 0,
                        "model_name": client.model,
                        "model_endpoint": client.endpoint,
                        "token_usage_input": 0,
                        "token_usage_output": 0,
                        "confidence_score": 0.0,
                        "thinking_content": "",
                        "schema_version": schema_version,
                        "prompt_version": prompt_version,
                        "validation_status": "pending",
                    },
                    ensure_ascii=False,
                )

        result_table = chunks_table.select(
            llm_result=pw.apply(
                extract_udf,
                pw.this.chunk_id,
                pw.this.source_file,
                pw.this.source_page,
                pw.this.source_page_end,
                pw.this.source_section,
                pw.this.source_position,
                pw.this.content,
                pw.this.content_type,
                pw.this.image_refs,
                pw.this.token_estimate,
            ),
        )

        # Route to all sinks
        return {name: result_table for name in ["json_output", "txt_fallback"]}
