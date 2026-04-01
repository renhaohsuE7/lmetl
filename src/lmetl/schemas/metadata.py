"""Metadata schemas for provenance, extraction tracking, and human validation."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExtractionMethod(str, Enum):
    DIRECT_PROMPT = "direct_prompt"
    INTERNAL_SKILL_API = "internal_skill_api"
    LANGCHAIN_SKILL = "langchain_skill"


class ImageMode(str, Enum):
    METADATA_ONLY = "metadata_only"
    VISION_LLM = "vision_llm"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


class ProvenanceMetadata(BaseModel):
    """Tracks where the extracted data came from in the source document."""

    source_file: str
    source_page: int = 0
    source_line: int = 0
    source_position: str = ""
    source_context: str = ""
    chunk_id: str = ""


class ExtractionProcessMetadata(BaseModel):
    """Tracks how the extraction was performed."""

    extraction_method: ExtractionMethod = ExtractionMethod.DIRECT_PROMPT
    extraction_mode: ImageMode = ImageMode.METADATA_ONLY
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: int = 0
    schema_version: str = "1.0"
    prompt_template_version: str = "1.0"


class ModelMetadata(BaseModel):
    """Tracks which model produced the extraction."""

    model_name: str = ""
    model_endpoint: str = ""
    token_usage_input: int = 0
    token_usage_output: int = 0
    confidence_score: float = 0.0
    thinking_content: Optional[str] = None


class SkillMetadata(BaseModel):
    """Tracks skill API info (for internal_skill_api / langchain_skill paths)."""

    skill_name: Optional[str] = None
    skill_version: Optional[str] = None
    skill_endpoint: Optional[str] = None
    raw_response: Optional[str] = None


class HumanValidationMetadata(BaseModel):
    """Tracks human review status."""

    validation_status: ValidationStatus = ValidationStatus.PENDING
    validator_id: Optional[str] = None
    validator_note: Optional[str] = None
    validated_at: Optional[datetime] = None


class ExtractionMetadata(BaseModel):
    """Complete metadata for a single extraction result."""

    provenance: ProvenanceMetadata
    extraction: ExtractionProcessMetadata = Field(default_factory=ExtractionProcessMetadata)
    model: ModelMetadata = Field(default_factory=ModelMetadata)
    skill: Optional[SkillMetadata] = None
    human_validation: HumanValidationMetadata = Field(default_factory=HumanValidationMetadata)


class ChunkRecord(BaseModel):
    """Represents a single document chunk in the pipeline."""

    chunk_id: str
    source_file: str
    source_page: int = 0
    source_section: str = ""
    source_position: str = ""
    chunk_index: int = 0
    content: str = ""
    content_type: str = "text"
    image_refs: str = "[]"
    token_estimate: int = 0


class ExtractionRecord(BaseModel):
    """A complete extraction result with data + metadata."""

    chunk_id: str
    source_file: str
    source_page: int = 0
    source_section: str = ""
    is_structured: bool = False
    extraction_result: Dict[str, Any] = Field(default_factory=dict)
    fallback_text: str = ""
    metadata: ExtractionMetadata
