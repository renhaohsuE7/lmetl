# lmetl 使用指南

> 適用版本：schema_version 1.1, prompts_version 1.1

---

## 1. YAML 配置檔

位置：`configs/base.yaml`

此 YAML 是 pipeline 的唯一控制點，包含：
- pwetl pipeline 定義（sources / transform / sinks）
- `lmetl` 區塊：模型參數、prompt 模板、schema 欄位定義

### 1.a 自訂 Prompt

`lmetl.prompts` 區塊控制所有 prompt 內容：

```yaml
prompts:
  system: |
    你是一位專業的文獻分析師...
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
```

- `system`：直接寫系統 prompt 全文，genre suffix 會自動附加
- `user_template`：使用 `{variable}` 佔位符，可用變數：
  - `{source_file}` — 檔名
  - `{source_section}` — 章節名
  - `{content}` — chunk 內容
  - `{extraction_instructions}` — 從 schema fields 自動產生
  - `{json_schema}` — 從 schema fields 自動產生

### 1.b 新增 Genre

在 `configs/genres/` 新增 YAML 檔案：

```yaml
# configs/genres/hydrology.yaml
system_prompt_suffix: |
  你具備水文學專業知識...
fields:
  - name: watershed
    type: str?
    description: 流域名稱
  - name: water_quality_params
    type: list[str]
    description: 水質參數
```

然後修改 `configs/base.yaml` 的 `extraction.genre: hydrology`，再執行 sync_schemas 產生 Pydantic model：

```bash
uv run python -m lmetl.tools.sync_schemas configs/base.yaml
```

支援的類型：`str`, `str?`, `int`, `int?`, `float`, `float?`, `list[str]`。可選 `constraints`（`ge`, `le`, `default`）。

---

## 2. Chunking 機制

**策略**：Heading-based（依 Heading 1–4 樣式切段）

**流程**：
1. python-docx 讀取 docx，逐段落掃描
2. 遇到 Heading 樣式 → 開啟新 section
3. 表格序列化為 markdown 併入所屬 section
4. 圖片記錄 metadata（`image_ref`, `page_estimate`）
5. 各 section 依 `max_tokens` 拆分為 chunk，段落間保留 `overlap_tokens` 重疊

**Token 估算**：CJK 字元 ×0.7 + ASCII 單詞 ×1（啟發式，非 tokenizer）

**配置**（YAML `sources[0].chunking`）：

| 參數 | 預設 | 說明 |
|------|------|------|
| `max_tokens` | 4000 | 每 chunk 最大 token 數 |
| `overlap_tokens` | 200 | 跨 chunk 重疊段落 |

**Provenance 欄位**：每個 chunk 攜帶 `source_section`（章節名）、`source_position`（heading + 頁碼 + 段落範圍）、`source_page` / `source_page_end`。

**已知限制**：python-docx 僅偵測明確 `<w:br type="page"/>` 分頁符號，無法推算 Word 渲染頁碼。段落索引是可靠的定位方式。

---

## 3. Chunk 輸出

Chunking 發生在記憶體中（DocxSource.read() → pw.Table），chunk 本身不寫檔。

**可檢視的輸出**：
- `output/extractions/*.json` — LLM 萃取結果（含每個 chunk 的 provenance + extraction）
- `output/fallback/*.txt` — JSON 解析失敗的 fallback
- `output/e2e_test/extraction_results.json` — E2E 測試產出，包含所有 chunk 的完整萃取結果

E2E 測試結果可直接用 `jq` 或文字編輯器閱讀：

```bash
cat output/e2e_test/extraction_results.json | python -m json.tool | less
```

---

## 4. E2E 測試報告摘要

完整報告：[e2e-test-report.md](e2e-test-report.md)

| 指標 | 結果 |
|------|------|
| 測試文件 | `[109]大屯火山群地區地熱探勘資料執行摘要.docx` (64 chunks) |
| 測試範圍 | 前 5 chunks |
| 成功率 | 5/5 (100%) |
| JSON 解析率 | 5/5 (100%) |
| 平均 confidence | 0.848 |
| 平均 latency | 48.2s/chunk (~32 tokens/s output) |
| 預估全檔耗時 | ~50 min (64 chunks × 48s) |

**品質亮點**：
- 書目資訊（title, institution, year）集中在前 2 chunks，後續正確回 null
- 地質欄位（岩石、地層、井名、探勘方法）萃取準確，無幻覺
- 即使短 chunk (143 tokens) 也能產出有意義的 recommendations 和 commentary

---

## 5. 測試方式

### Unit Tests（不需 Ollama）

```bash
uv run pytest tests/ -v               # 全部 41 tests
uv run pytest tests/test_chunking.py   # 僅 chunking
uv run pytest tests/test_schema_loader.py  # schema loader
```

### E2E Tests（需 Ollama + 測試檔案）

```bash
# 前提：Ollama 服務在 192.168.9.160:11434 且已載入 gpt-oss:120b
uv run pytest tests/test_e2e.py -v -s

# 自訂 endpoint/model
OLLAMA_ENDPOINT=http://localhost:11434 OLLAMA_MODEL=qwen2:72b \
  uv run pytest tests/test_e2e.py -v -s
```

E2E 測試會自動 skip 如果 Ollama 不可達或測試檔案不存在。

### Schema 一致性檢查

```bash
uv run python -m lmetl.tools.sync_schemas --check configs/base.yaml
```

### 測試結果（2026-04-01）

- Unit: **41/41 passed** (0.54s)
- E2E: **5/5 chunks passed** (242s), avg confidence 0.848
