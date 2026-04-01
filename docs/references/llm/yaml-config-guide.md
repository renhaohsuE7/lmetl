# YAML 配置與 Schema 同步工具指南

## 設計原則

**YAML 為 Single Source of Truth** — 模型參數、Prompt 模板、Schema 欄位定義全部集中在 YAML config 裡。Python code 只負責讀取和執行，不定義任何萃取邏輯。

---

## 配置結構

所有 lmetl 配置位於 pipeline YAML 的 `lmetl:` section。

### 1. 模型推理參數

```yaml
lmetl:
  llm:
    endpoint: ${OLLAMA_ENDPOINT:http://192.168.9.160:11434}
    model: ${OLLAMA_MODEL:gpt-oss:120b}
    timeout: 300
    max_retries: 3
    parameters:          # 全部 optional，有填才傳給 API
      temperature: 0.1
      top_k: 40
      top_p: 0.9
      min_p: 0.05
      repeat_penalty: 1.1
      num_predict: 4096  # max output tokens
```

- `endpoint` / `model` 支援環境變數覆寫（`${VAR:default}` 語法）
- `parameters` 內的每個 key 都是 optional，未填就不傳，由 Ollama/vLLM 使用預設值
- 不同模型建不同 YAML 檔（如 `dig_info_geology_qwen.yaml`），各帶最佳參數組合

### 2. Prompt 模板

```yaml
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
```

- `system`: 完整 system prompt，genre 的 `system_prompt_suffix` 會自動附加在末尾
- `user_template`: 使用 `{variable}` 佔位，runtime 由 `PromptBuilder` 替換：
  - `{source_file}` — 來源檔名
  - `{source_section}` — 章節標題
  - `{content}` — chunk 內容
  - `{extraction_instructions}` — 從 schema fields 自動產生的萃取指示
  - `{json_schema}` — 從 schema fields 自動產生的 JSON Schema
- 改 prompt 只需編輯 YAML，Docker volume mount 即時生效，不需重建 image

### 3. Schema 欄位定義

```yaml
  extraction:
    core: true
    genre: geology
    schema_version: "1.1"

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
        - name: confidence_score
          type: float
          description: 信心分數 (0.0-1.0)
          constraints:
            ge: 0.0
            le: 1.0
            default: 0.0
        # ...完整欄位見 configs/dig_info_geology.yaml

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
          # ...完整欄位見 configs/dig_info_geology.yaml
```

每個 field 的 `description` 有兩個用途（由 runtime 自動處理）：
1. 產生 prompt 中的萃取指示（如 `- rock_types: 岩石類型`）
2. 產生 JSON Schema 給 LLM 參考

#### Type 對照表

| YAML type | Python | JSON Schema | 說明 |
|-----------|--------|-------------|------|
| `str` | `str` | `string` | 必填字串 |
| `str?` | `Optional[str]` | `string \| null` | 可為 null |
| `int` | `int` | `integer` | 必填整數 |
| `int?` | `Optional[int]` | `integer \| null` | 可為 null |
| `float` | `float` | `number` | 必填浮點數 |
| `list[str]` | `List[str]` | `array of string` | 字串列表（預設空 `[]`） |

---

## Schema 同步策略

```
YAML fields (人寫/維護)
  │
  ├─→ [Runtime] PromptBuilder 動態產生 prompt + JSON schema
  │
  └─→ [CLI tool] sync_schemas 產出 Pydantic model .py
       │
       └─→ [CI] --check mode 比對 YAML 與 .py 是否一致
```

### 為什麼保留 Pydantic model？

YAML 已經是 source of truth，但 Pydantic model .py 仍有價值：
- **Output validation** — 萃取結果可用 `CoreExtractionResult.model_validate()` 驗證
- **IDE 補全** — 開發時有 type hint
- **Import 使用** — 其他模組可直接 `from lmetl.schemas.core import CoreExtractionResult`

關鍵：**Pydantic .py 由工具產生，不手動編輯。**

### sync_schemas 工具使用方式

```bash
# 從 YAML 產生/更新 Pydantic model 檔案
uv run python -m lmetl.tools.sync_schemas configs/dig_info_geology.yaml

# 只檢查是否同步（CI 用），不寫入檔案
uv run python -m lmetl.tools.sync_schemas --check configs/dig_info_geology.yaml
```

產出檔案：
- `src/lmetl/schemas/core.py` — Core schema Pydantic model
- `src/lmetl/schemas/genres/geology.py` — Geology genre Pydantic model

---

## 常見操作

### 調整 prompt 措辭

1. 編輯 `configs/dig_info_geology.yaml` 的 `prompts.system` 或 `prompts.user_template`
2. 重跑萃取（Docker volume mount 自動生效，不需 rebuild）

### 調整模型推理參數

1. 編輯 `configs/dig_info_geology.yaml` 的 `llm.parameters`
2. 重跑萃取

### 新增 Genre

1. 在 YAML 的 `schemas.genres` 下新增 section：
   ```yaml
   genres:
     hydrology:
       system_prompt_suffix: |
         你同時具備水文地質專業知識...
       fields:
         - name: aquifer_type
           type: str?
           description: 含水層類型
         - name: water_table_depth
           type: str?
           description: 地下水位深度
   ```
2. 修改 `extraction.genre: hydrology`
3. 執行 `uv run python -m lmetl.tools.sync_schemas configs/xxx.yaml` 產生 Pydantic model

### 新增 / 修改欄位

1. 在 YAML 的 `schemas.core.fields` 或 `schemas.genres.xxx.fields` 增刪改
2. 執行 `sync_schemas` 更新 Pydantic model
3. 重跑萃取

### 為不同模型建立配置

```bash
cp configs/dig_info_geology.yaml configs/dig_info_geology_qwen.yaml
# 編輯 model, parameters, 可能也調 prompt
```

---

## 相關文件

| 文件 | 說明 |
|------|------|
| `configs/dig_info_geology.yaml` | 主要 pipeline 配置（含完整 lmetl section） |
| `docs/plans/project/architecture-questions.md` Q7 | 配置架構設計決定 |
| `docs/plans/llm/yaml-config-migration.md` | 從 Phase 1 遷移的詳細實作計畫 |
| `src/lmetl/utils/schema_loader.py` | YAML schema 讀取 + 動態產生（實作中） |
| `src/lmetl/tools/sync_schemas.py` | CLI 同步工具（實作中） |
