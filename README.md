# LMETL

**ETL + LLM = structured information in JSON**

使用 LLM 從文獻/研究報告（docx）萃取資訊並結構化，輸出為 JSON。

**目的：**
- 提供 Agent Tool 透過 API 取得處理後的文獻資訊
- 為 RAG 提供另一個結構化查詢選項

```
DocxSource → LLMTransform (Ollama) → JsonExtractionSink + TxtFallbackSink
```

## Configuration

所有萃取配置集中在 YAML，包含模型參數、prompt 模板、schema 欄位定義。預設：`configs/<domain>.yaml`。

**自訂 Genre 範例**：假設要建立物理學文獻萃取，在 YAML `lmetl.schemas.genres` 下新增 `physics` 區塊：

```yaml
# configs/physics_papers.yaml
lmetl:
  extraction:
    genre: physics          # 指定使用 physics genre
  schemas:
    genres:
      physics:
        system_prompt_suffix: |
          你具備物理學專業知識，擅長辨識方程式、實驗方法與物理量。
        fields:
          - name: equations
            type: list[str]
            description: 文中提及的重要方程式
          - name: physical_quantities
            type: list[str]
            description: 關鍵物理量及其數值
          - name: experiment_methods
            type: list[str]
            description: 實驗方法與裝置
```

執行 `sync_schemas` 從 YAML 自動產生對應的 Pydantic model（`schemas/genres/physics.py`）：

```bash
# 產生 schema
uv run python -m lmetl.tools.sync_schemas configs/physics_papers.yaml

# 驗證 schema 是否與 YAML 同步（CI 可用）
uv run python -m lmetl.tools.sync_schemas --check configs/physics_papers.yaml
```

詳細說明：[Usage Guide](docs/references/llm/usage-guide.md) | [YAML Config Guide](docs/references/llm/yaml-config-guide.md)

## Dependency: pwetl

本專案作為 [pwetl](https://github.com/sw-willie-wu/pwetl) 的consumer，使用其：

- **Plugin 架構** — BaseSource / BaseTransform / BaseSink 抽象介面，lmetl 的 DocxSource、LLMTransform、JsonExtractionSink 皆繼承自 pwetl base classes
- **YAML Config 驅動** — Pipeline 配置（sources、transform、sinks）遵循 pwetl YAML convention
- **Factory/Registry Pattern** — 元件註冊與動態載入機制
- **Pathway 整合** — 基於 Pathway 的 streaming table 運算與資料流

pwetl 處理 ETL 框架層，lmetl 專注在 LLM 萃取邏輯與 domain-specific schema。

## Quick Start

```bash
# Install dependencies
uv sync

# Run extraction on a docx file (requires Ollama)
uv run python -m lmetl.tools.run_extraction data/your_report.docx

# Limit to first N chunks (for testing)
uv run python -m lmetl.tools.run_extraction data/your_report.docx --max-chunks 5

# Run pipeline via pwetl
LMETL_CONFIG=configs/dig_info_geology.yaml docker compose up app
```

輸出：`output/extractions/<filename>.json`

## Testing

```bash
uv run pytest tests/ -v                # Unit tests (41 tests, 不需 Ollama)
uv run pytest tests/test_e2e.py -v -s  # E2E (需 Ollama + 測試檔案，自動 skip 如不可達)
```

E2E 測試結果（2026-04-01）：5/5 chunks 成功，平均 confidence 0.848，平均 latency 48.2s/chunk。詳見 [E2E Test Report](docs/references/llm/e2e-test-report.md)。

### 跑一個完整檔案測試

```sh
uv run python -m lmetl.tools.run_extraction "filename"
```

## Documentation

| Document | Description |
|----------|-------------|
| [Usage Guide](docs/references/llm/usage-guide.md) | YAML 配置、prompt 自訂、genre 新增、chunking 機制、測試方式 |
| [E2E Test Report](docs/references/llm/e2e-test-report.md) | 萃取品質、效能數據、已知問題 |
| [YAML Config Guide](docs/references/llm/yaml-config-guide.md) | Config structure, schema sync tool |
| [Architecture Decisions (Q1-Q7)](docs/plans/project/architecture-questions.md) | Design decisions and rationale |
| [YAML Migration Plan](docs/plans/llm/yaml-config-migration.md) | Implementation plan for YAML-driven config |
| [pwetl Analysis](docs/references/project/pwetl-analysis.md) | Reference project analysis |

## Inspired By

- [pwetl](https://github.com/sw-willie-wu/pwetl) — Plugin architecture, YAML config, Factory/Registry pattern

- [**ChangChunCheng** (JackyChang)](https://github.com/ChangChunCheng)
- [**sw-willie-wu** (S.W.)](https://github.com/sw-willie-wu)

Special thanks to those people above for the foundational architecture and inspiration.
