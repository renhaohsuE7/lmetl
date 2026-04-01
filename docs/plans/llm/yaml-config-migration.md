# YAML 配置遷移計畫

> 從 Phase 1 的 hardcoded Python → YAML-driven 配置架構

## 背景

Phase 1 E2E 測試驗證萃取品質可行（2/2 chunks 成功，confidence 0.78-0.96），但配置散落 Python 各處，不利調優與擴充。詳見 [Q7 決定](../project/architecture-questions.md#q7-配置架構prompt--model-parameters--schema)。

---

## 目標 YAML 結構

```yaml
# configs/base.yaml — lmetl section

lmetl:

  # ── 模型配置 ──
  llm:
    endpoint: ${OLLAMA_ENDPOINT:http://192.168.9.160:11434}
    model: ${OLLAMA_MODEL:gpt-oss:120b}
    timeout: 300
    max_retries: 3
    parameters:               # 全部 optional，有填才傳
      temperature: 0.1
      top_k: 40
      top_p: 0.9
      min_p: 0.05
      repeat_penalty: 1.1
      num_predict: 4096       # max output tokens

  # ── Prompt 模板 ──
  prompts:
    version: "1.1"
    system: |
      你是一位專業的文獻分析師，負責從研究報告中萃取結構化資訊。
      請根據提供的文件段落，萃取所要求的欄位。
      回覆必須是合法的 JSON 格式，符合指定的 schema。
      如果某個欄位在文件中找不到相關資訊，請設為 null 或空陣列。
      請附上 confidence_score (0.0-1.0) 表示你對萃取結果的信心程度。
      請附上 thinking 欄位，簡述你的推理過程。
    user_template: |
      ## 文件：{source_file}
      ## 章節：{source_section}

      ## 內容：
      {content}

      ## 萃取要求：
      {extraction_instructions}

      ## JSON Schema：
      ```json
      {json_schema}
      ```

      請以合法 JSON 回覆，不要加入任何其他文字。

  # ── 萃取設定 ──
  extraction:
    core: true
    genre: geology
    schema_version: "1.1"

  # ── Schema 欄位定義 ──
  schemas:
    core:
      system_prompt_suffix: ""
      fields:
        - name: title
          type: str?
          description: 文件標題
        - name: authors
          type: list[str]
          description: 作者列表
        - name: institution
          type: str?
          description: 執行單位
        - name: date
          type: str?
          description: 日期
        - name: year
          type: int?
          description: 年度（整數）
        - name: abstract
          type: str?
          description: 摘要
        - name: key_findings
          type: list[str]
          description: 關鍵發現（列表）
        - name: llm_recommendations
          type: list[str]
          description: 基於內容的延伸建議（列表）
        - name: llm_commentary
          type: str?
          description: 你對這段內容的專業評析
        - name: confidence_score
          type: float
          description: 信心分數 (0.0-1.0)
          constraints:
            ge: 0.0
            le: 1.0
            default: 0.0
        - name: thinking
          type: str?
          description: 推理過程

    genres:
      geology:
        system_prompt_suffix: |
          你同時具備地質學與地熱能源專業知識，
          能辨識岩性、地層、溫度梯度、鑽井資訊等專業術語。
        fields:
          - name: rock_types
            type: list[str]
            description: 岩石類型
          - name: formations
            type: list[str]
            description: 地層名稱
          - name: geological_age
            type: str?
            description: 地質年代
          - name: temperature_gradient
            type: str?
            description: 溫度梯度
          - name: drilling_depth
            type: str?
            description: 鑽井深度
          - name: well_names
            type: list[str]
            description: 井名列表
          - name: geothermal_assessment
            type: str?
            description: 地熱資源評估
          - name: exploration_methods
            type: list[str]
            description: 探勘方法
```

---

## Type Mapping（YAML → Python / JSON Schema）

| YAML type | Python type | JSON Schema type | Pydantic |
|-----------|-------------|------------------|----------|
| `str` | `str` | `{"type": "string"}` | `str` |
| `str?` | `Optional[str]` | `{"type": ["string", "null"]}` | `Optional[str] = None` |
| `int` | `int` | `{"type": "integer"}` | `int` |
| `int?` | `Optional[int]` | `{"type": ["integer", "null"]}` | `Optional[int] = None` |
| `float` | `float` | `{"type": "number"}` | `float` |
| `list[str]` | `List[str]` | `{"type": "array", "items": {"type": "string"}}` | `List[str] = Field(default_factory=list)` |

---

## 實作步驟

### Step 1: Schema loader (`utils/schema_loader.py`)

從 YAML 讀取 `schemas` section，提供：

```python
class SchemaLoader:
    def __init__(self, config: dict):
        """接受 lmetl config dict"""

    def get_fields(self, section: str) -> list[dict]:
        """回傳 core 或指定 genre 的 fields list"""

    def get_system_prompt_suffix(self, genre: str) -> str:
        """回傳 genre 的 system_prompt_suffix"""

    def build_json_schema(self, core: bool, genre: str | None) -> dict:
        """合併 core + genre fields → JSON Schema dict"""

    def build_extraction_instructions(self, core: bool, genre: str | None) -> str:
        """從 fields 的 name + description → 中文萃取指示文字"""

    def build_pydantic_model(self, section: str) -> type[BaseModel]:
        """動態產 Pydantic model（用 pydantic.create_model）"""
```

### Step 2: 重構 PromptBuilder

```python
class PromptBuilder:
    def __init__(self, config: dict):
        """接受完整 lmetl config dict"""
        self.schema_loader = SchemaLoader(config)
        self.prompts_config = config.get("prompts", {})
        self.extraction_config = config.get("extraction", {})

    def build_system_prompt(self) -> str:
        base = self.prompts_config["system"]
        genre = self.extraction_config.get("genre")
        if genre:
            suffix = self.schema_loader.get_system_prompt_suffix(genre)
            base += "\n" + suffix
        return base

    def build_user_prompt(self, chunk: dict) -> str:
        template = self.prompts_config["user_template"]
        core = self.extraction_config.get("core", True)
        genre = self.extraction_config.get("genre")

        instructions = self.schema_loader.build_extraction_instructions(core, genre)
        json_schema = self.schema_loader.build_json_schema(core, genre)

        return template.format(
            source_file=chunk.get("source_file", "unknown"),
            source_section=chunk.get("source_section", ""),
            content=chunk.get("content", ""),
            extraction_instructions=instructions,
            json_schema=json.dumps(json_schema, ensure_ascii=False, indent=2),
        )
```

### Step 3: 重構 LLMClient

- 從 YAML `llm.parameters` 讀取推理參數
- `extract()` 時只傳有值的參數（不傳 None）

```python
class LLMClient:
    def __init__(self, llm_config: dict):
        self.endpoint = llm_config["endpoint"]
        self.model = llm_config["model"]
        self.timeout = llm_config.get("timeout", 300)
        self.max_retries = llm_config.get("max_retries", 3)
        self.parameters = llm_config.get("parameters", {})
        # ...

    def extract(self, system_prompt, user_prompt):
        kwargs = {
            "model": self.model,
            "messages": [...],
        }
        # 只傳有值的推理參數
        for key in ["temperature", "top_k", "top_p", "min_p",
                     "repeat_penalty", "num_predict"]:
            if key in self.parameters:
                kwargs[key] = self.parameters[key]
        # ...
```

### Step 4: 更新 YAML config

- 把現有 `configs/base.yaml` 的 `lmetl` section 擴充為完整結構
- 移除 `prompt_template_version`（改用 `prompts.version`）

### Step 5: CLI tool `sync_schemas`

```bash
uv run python -m lmetl.tools.sync_schemas configs/base.yaml
```

- 讀取 YAML `schemas` section
- 產出 `src/lmetl/schemas/core.py` 和 `src/lmetl/schemas/genres/geology.py`
- 印出 diff 讓使用者確認
- `--check` mode：只比對不寫入，CI 用

### Step 6: 測試更新

- 更新現有 unit tests 改用 config dict 初始化
- E2E test 不需改（它已經直接用 PromptBuilder + LLMClient）
- 新增 test：schema_loader 的 type mapping、JSON schema 產生、instruction 產生

### Step 7: 刪除 hardcoded prompts

- 刪除 `prompts.py` 中的 `_core_instructions()`、`_geology_instructions()`
- 刪除 `build_system_prompt()` 中的 `if self.genre == "geology"` 硬寫邏輯
- 所有 genre-specific 邏輯改由 YAML 驅動

---

## 影響範圍

| 檔案 | 變更 |
|------|------|
| `configs/base.yaml` | 擴充 lmetl section（prompts + schemas） |
| `src/lmetl/utils/schema_loader.py` | **新增** — YAML schema 讀取 + 動態產生 |
| `src/lmetl/llm/prompts.py` | **重構** — 改為 YAML-driven |
| `src/lmetl/llm/client.py` | **擴充** — 支援完整推理參數 |
| `src/lmetl/transforms/llm_transform.py` | **小改** — 傳 config dict 給 PromptBuilder |
| `src/lmetl/schemas/core.py` | 改為由 sync_schemas 工具產生 |
| `src/lmetl/schemas/genres/geology.py` | 改為由 sync_schemas 工具產生 |
| `src/lmetl/tools/sync_schemas.py` | **新增** — CLI 同步工具 |
| `tests/` | 更新 + 新增 schema_loader 測試 |

---

## 驗收標準

1. `uv run pytest tests/ -v` — 全部通過
2. YAML 中改 prompt 或新增 genre field → 不需改任何 Python code
3. `uv run python -m lmetl.tools.sync_schemas --check configs/base.yaml` — 通過
4. E2E 萃取結果品質不低於 Phase 1（confidence ≥ 0.78）
5. YAML 中加完整推理參數 → LLM client 正確傳遞
