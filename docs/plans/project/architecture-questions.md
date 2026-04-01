# 架構與方向待討論事項

## 前置決定：專案定位

> **決定：獨立專案（不 Fork），以 pwetl 作為 library 依賴**
> - `pip install pwetl`（或 `pip install git+https://github.com/sw-willie-wu/pwetl.git`）
> - 直接使用 pwetl 的 BaseSource / BaseTransform / BaseSink 繼承擴充
> - 現成模組（FileSource、FileSink 等）直接用，不重複造輪子
> - 自建：PDFSource、HTMLSource、LLMTransform 等文獻 + LLM 專用模組
> - 沿用 pwetl 的 YAML 配置驅動方式
> - 專案定位：pwetl 的下游應用 / 擴充套件，專注非結構化文獻 + LLM 萃取
> - README 致謝 pwetl
> - 詳見 [pwetl 分析](../../references/project/pwetl-analysis.md)

---

## 總覽

```
文獻 (PDF/HTML/TXT/...)
        │
        ▼
   ┌─────────┐
   │ Extract  │  解析文件、切 chunk、OCR (如需要)
   └────┬────┘
        │  raw text / structured chunks
        ▼
   ┌─────────────┐
   │ Transform   │  LLM 根據 schema/prompt 萃取結構化資訊
   │  (LLM核心)  │
   └────┬────────┘
        │  structured data
        ▼
   ┌─────────┐
   │  Load    │  寫入 JSON / SQLite / PostgreSQL / plain TXT
   └─────────┘
```

---

## Q1: 文獻來源與格式

- [x] 主要格式：**docx**（目前全部為 .docx，100-200MB，含大量圖片）、**PDF**（未來會有）
- [x] 文獻領域：**地質 / 地熱 / 鑽探**政府研究報告（中文）
- [x] 文字萃取工具：`python-docx`（docx）、`pypdf`（PDF）
- [x] 圖片處理：**兩種模式皆支援，參數控制切換**
  - `metadata_only`（預設）：記錄 metadata（頁碼、檔名、前後文、簡易摘要），速度快
  - `vision_llm`：多模態 LLM 分析圖片內容（地質圖、鑽井柱狀圖、數據表格…），較耗時
- [x] 圖片萃取時需附帶 metadata：頁碼、檔名、前後文、簡易摘要

### LLM 任務類型（已識別）

| 任務 | 資料夾 | 說明 |
|------|--------|------|
| dig_info | `data/dig_info_from_pdf_mission_data/` | 從單份報告萃取資訊 |
| compare | `data/compare_mission_data/` | 跨報告比對分析 |

> **Q1 決定：已確認**

---

## Q2: 萃取目標

### Core Schema（所有文獻預設萃取）

- [x] 基本欄位：標題、作者/執行單位、日期/年度、摘要
- [x] 關鍵結論 / 發現
- [x] LLM 建議（基於文獻內容的延伸建議）
- [x] LLM 評析（commentary / critique — 需定義正式用語或允許帶幽默感，待確認風格）

### Genre Schema（依文獻領域額外萃取，可插拔）

以 `geology` genre 為例（Phase 1 E2E 驗證完畢）：
- [x] `rock_types`: `list[str]` — 岩石類型（安山岩、火成岩、沉積岩…）
- [x] `formations`: `list[str]` — 地層名稱（五指山層、漸新世沉積岩…）
- [x] `geological_age`: `str?` — 地質年代（Pliocene ~3 Ma）
- [x] `temperature_gradient`: `str?` — 溫度梯度（報告未提供時回 null）
- [x] `drilling_depth`: `str?` — 鑽井深度（報告未提供時回 null）
- [x] `well_names`: `list[str]` — 井名列表（E208、SHP-1、Chinshan-1…）
- [x] `geothermal_assessment`: `str?` — 地熱資源評估（整體潛能判斷）
- [x] `exploration_methods`: `list[str]` — 探勘方法（MT、磁力、重力、鑽探…）

E2E 驗證結果（[109]大屯火山群地區地熱探勘資料執行摘要.docx）：
- Chunk 0（摘要段，3948 tokens）：19 個 key 全數回傳，confidence 0.96
- Chunk 1（前言段，431 tokens）：地質欄位正確回空/null，confidence 0.78
- 詳見 `output/e2e_test/extraction_results.json`

### 設計原則

- **Core** schema 為內建預設，每次萃取必跑
- **Genre** schema 為可插拔模組，依 YAML config 指定啟用哪個 genre
- 未來可擴充其他 genre（`medical`、`legal`、`patent`…）
- Q7 決定：Schema 定義移至 YAML 為 single source of truth，詳見 [Q7](#q7-配置架構prompt--model-parameters--schema)

```yaml
extraction:
  core: true           # 永遠開啟
  genre: geology       # 載入地質 genre schema
```

> **Q2 決定：架構確認（Core + Genre），Geology genre 8 欄位已定義且 E2E 驗證通過**

---

## Q3: LLM 選擇

- [x] **本地模型為主**，第三方外部 API 為輔（暫不實作）
- [x] Ollama：`http://192.168.9.160:11434`，常駐 `gpt-oss:120b`
- [x] 未來：vLLM + Ray 服務（同事提供）、OpenAI-compatible API
- [x] 多 provider 切換：需要，但初期只實作 Ollama，架構預留擴充點

### Provider 優先級

| 優先級 | Provider | 狀態 | 介面 |
|--------|----------|------|------|
| 1 | Ollama | 已可用 | `http://192.168.9.160:11434` |
| 2 | vLLM + Ray | 未來 | OpenAI-compatible API |
| 3 | 外部 API（Claude / OpenAI） | 暫不實作 | 預留介面 |

### 設計考量

- 統一用 OpenAI-compatible API 格式作為抽象層（Ollama / vLLM 都支援）
- YAML config 指定 provider endpoint + model name
- 成本：本地模型無 token 費用，主要考量推論速度

> **Q3 決定：已確認**

---

## Q4: 輸出格式

### 優先級

| 優先級 | 格式 | 用途 |
|--------|------|------|
| 1 | **JSON** | 主要輸出，結構化萃取結果 |
| 2 | **DB**（SQLite / PostgreSQL） | 查詢統計 |
| 3 | **Plain TXT** | 例外處理：缺乏規律但被判定為重要的資訊 |

### TXT 的特殊定位

- TXT 不是常規輸出格式，而是 **fallback**
- 當 rule-based 或 LLM-based ETL 判定某段內容重要，但無法歸入結構化 schema 時，以 TXT 保留原文
- 可視為「待人工處理」的暫存區

> **Q4 決定：已確認**

---

## Q5: 規模與效能

### 使用情境

- [x] 此 ETL 在既有 LLM RAG 流程中被觸發
- [x] 典型使用：user 上傳 1~3 份文件 → ETL 萃取 → 結果進 RAG
- [x] 每份文件頁數很多（100MB+ docx，數百頁含圖）

### 開發階段

| 階段 | 檔案數 | 重點 | 狀態 |
|------|--------|------|------|
| Phase 1 | 1~3 份 | 單檔 pipeline 跑通，處理大頁數文件 | **優先實作** |
| Phase 2 | 數十份 | batch processing、並行處理 | 暫不處理，待 Phase 1 測試結果 |
| Phase 3 | 百份以上 | 佇列管理、增量更新、排程 | 暫不處理，待 Phase 2 測試結果 |

### 單檔效能挑戰（Phase 1 核心問題）

- 大型 docx（數百頁）→ chunking 策略是關鍵
- LLM context window 限制 vs 文件長度 → 需分段送 LLM
- 圖片量大 → vision_llm 模式下推論時間長
- [x] chunking 策略：heading-based（Heading 1/2/3/4 分 section），超過 max_tokens 再依段落切分，帶 overlap
- [ ] 分段結果如何合併為完整萃取結果（Phase 2）

> **Q5 決定：Phase 1 小規模優先，Phase 2/3 預留但暫不處理**

---

## Q6: 品質控制與 Metadata

### 萃取來源（extraction_method）

萃取不只走 LLM prompt，至少有三種路徑：

| 路徑 | extraction_method | 說明 |
|------|-------------------|------|
| A | `direct_prompt` | 直接對 LLM 下 prompt |
| B | `internal_skill_api` | 呼叫公司內部 LLM skill API |
| C | `langchain_skill` | 本專案自建 LangChain skill |

### Metadata Schema（每筆萃取結果必帶）

**來源追溯（Provenance）**

| Key | 說明 |
|-----|------|
| `source_file` | 原始檔名 |
| `source_page` | 頁碼 |
| `source_line` | 行數 |
| `source_position` | 位置描述 |
| `source_context` | 原文段落（佐證引用） |
| `chunk_id` | 從哪個 chunk 萃取 |

**萃取過程（Extraction）**

| Key | 說明 |
|-----|------|
| `extraction_method` | `direct_prompt` / `internal_skill_api` / `langchain_skill` |
| `extraction_mode` | `metadata_only` / `vision_llm`（圖片相關） |
| `extracted_at` | 萃取時間 |
| `latency_ms` | 耗時 |
| `schema_version` | core/genre schema 版本 |
| `prompt_template_version` | prompt 模板版本（路徑 A/C） |

**模型資訊（Model）**

| Key | 說明 |
|-----|------|
| `model_name` | 模型名稱 |
| `model_endpoint` | API endpoint |
| `token_usage_input` | 輸入 tokens |
| `token_usage_output` | 輸出 tokens |
| `confidence_score` | LLM 自評信心 |
| `thinking_content` | reasoning model 的推理過程 |

**Skill 資訊（路徑 B/C 專用）**

| Key | 說明 |
|-----|------|
| `skill_name` | skill 名稱 |
| `skill_version` | skill 版本 |
| `skill_endpoint` | skill API endpoint（路徑 B） |
| `raw_response` | skill 原始 response（除錯/稽核用） |

**人工審查（Human Validation）**

| Key | 說明 |
|-----|------|
| `validation_status` | `pending` / `approved` / `rejected` / `needs_revision` |
| `validator_id` | 審查人員 ID |
| `validator_note` | 審查備註 |
| `validated_at` | 審查時間 |

> 未來規劃：API endpoint for human validation + Web UI（前端 RD 協作）

> **Q6 決定：已確認**

---

## Q7: 配置架構（Prompt / Model Parameters / Schema）

### 現況問題

Phase 1 驗證後發現配置散落三處：

| 類別 | Phase 1 位置 | 問題 |
|------|-------------|------|
| 模型參數（endpoint, model, timeout, temperature） | YAML `lmetl.llm` | 不完整，缺 top_k/top_p/min_p/repeat_penalty/num_predict |
| System prompt | Python `prompts.py` 硬寫 | 改措辭要改 code、重建 Docker |
| User prompt 模板 | Python `prompts.py` 硬寫 | 同上 |
| Core 欄位說明 | Python `prompts.py` 硬寫 | 同上 |
| Genre 欄位說明 | Python `prompts.py` 硬寫 | 同上 |
| Genre schema | Python `geology.py` Pydantic model | 新增 genre 要寫 Python |
| Core schema | Python `core.py` Pydantic model | 改欄位要改 Python + prompt 兩處 |
| `prompt_template_version` | YAML | 有 version 號但 prompt 實際內容在 Python，形同虛設 |

核心矛盾：**YAML 聲稱是配置驅動，但大半配置寫死在 Python 裡。**

### 決定：YAML 為 Single Source of Truth

所有配置集中到 YAML，包含：

#### 1. 模型推理參數（完整）

```yaml
lmetl:
  llm:
    endpoint: ${OLLAMA_ENDPOINT:http://192.168.9.160:11434}
    model: ${OLLAMA_MODEL:gpt-oss:120b}
    timeout: 300
    max_retries: 3
    parameters:
      temperature: 0.1
      top_k: 40
      top_p: 0.9
      min_p: 0.05
      repeat_penalty: 1.1
      num_predict: 4096
```

- 不同模型可建不同 YAML（如 `dig_info_geology_qwen.yaml`），各帶最佳參數
- `parameters` 為 optional，有填才傳，讓 Ollama/vLLM 各自用 default

#### 2. Prompt 模板

```yaml
  prompts:
    version: "1.0"
    system: |
      你是一位專業的文獻分析師，負責從研究報告中萃取結構化資訊。
      ...
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

- `system` 為完整 system prompt，genre 的 `system_prompt_suffix` 會自動附加
- `user_template` 用 `{variable}` 佔位，runtime 替換
- 改 prompt 只改 YAML，不動 Python，Docker volume mount 即時生效

#### 3. Schema 欄位定義（Core + Genre）

```yaml
  schemas:
    core:
      fields:
        - name: title
          type: str?
          description: 文件標題
        - name: authors
          type: list[str]
          description: 作者列表
        # ...

    genres:
      geology:
        system_prompt_suffix: |
          你同時具備地質學與地熱能源專業知識，
          能辨識岩性、地層、溫度梯度、鑽井資訊等專業術語。
        fields:
          - name: rock_types
            type: list[str]
            description: 岩石類型
          # ...
```

- 新增 genre = 在 `genres:` 下加一個 section
- 每個 field 的 `description` 同時用於：prompt instruction 產生 + JSON schema 產生

### Schema 同步策略（YAML ↔ Pydantic）

YAML fields 為 source of truth，Pydantic model 從 YAML 產生：

```
YAML fields (人寫/維護)
  │
  ├→ Runtime: 動態產 prompt instructions + JSON schema
  │
  └→ CLI tool: 產出 Pydantic model .py（開發時 type safety / IDE 補全用）
       └→ CI check: 比對 YAML 與 .py 是否一致
```

- **Runtime 用途**：`PromptBuilder` 從 YAML fields 動態建 prompt + JSON schema
- **開發用途**：CLI tool `sync_schemas` 從 YAML 產出 `core.py` / `geology.py`
- **CI 護欄**：檢查 YAML fields 和 Pydantic .py 是否同步，不一致就 fail

Pydantic model 保留的價值：output validation、IDE 補全、type safety。
不再由人手動維護，改由工具從 YAML 自動產生。

### 好處

1. **一個 YAML 看到全部** — model params + prompt + schema 不用跳檔案
2. **換模型不改 code** — 不同模型建不同 YAML，帶不同 parameters 和 prompt
3. **prompt 調優不重建 Docker** — YAML 透過 volume mount 即時生效
4. **新增 genre 不改 Python** — 加一個 `genres.xxx` section 即可
5. **版控清楚** — git diff 看到 prompt/參數/schema 的每次變更

> **Q7 決定：YAML 為 single source of truth，Pydantic 由工具從 YAML 產生，保留用於 validation + IDE 補全**
