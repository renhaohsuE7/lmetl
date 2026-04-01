# E2E 測試報告

> 測試日期：2026-04-01
> 配置版本：YAML-driven (schema_version 1.1, prompts_version 1.1)

---

## 測試環境

| 項目 | 值 |
|------|-----|
| 模型 | `gpt-oss:120b` (Ollama) |
| Endpoint | `http://192.168.9.160:11434` |
| 推理參數 | temperature=0.1, top_k=40, top_p=0.9, min_p=0.05, repeat_penalty=1.1, num_predict=4096 |
| 測試文件 | `[109]大屯火山群地區地熱探勘資料執行摘要.docx` (~104 MB) |
| Chunking | heading-based, max_tokens=4000, overlap_tokens=200 |
| 文件 chunks 總數 | 64 |
| 測試 chunks | 5 (前 5 個 section) |

---

## 效能數據

### 整體

| 指標 | 值 |
|------|-----|
| 測試總時間 | 242s (4m02s) |
| 成功率 | 5/5 (100%) |
| 平均 confidence | 0.848 |
| JSON 解析成功率 | 5/5 (100%) |

### 各 Chunk 詳細

| Chunk | Section | Tokens (est.) | Latency | Tokens In | Tokens Out | Confidence |
|-------|---------|--------------|---------|-----------|------------|------------|
| 0 | 大屯火山群地區 | 3,948 | 97.0s | 6,871 | 2,771 | 0.96 |
| 1 | 前言 | 431 | 35.5s | 1,876 | 1,319 | 0.78 |
| 2 | 概述 | 334 | 36.0s | 1,736 | 1,354 | 0.78 |
| 3 | 地熱地質背景 | 392 | 42.0s | 1,859 | 1,547 | 0.86 |
| 4 | 文獻回顧與調查更新資訊 | 143 | 30.6s | 1,463 | 1,151 | 0.86 |

### 效能分析

- **平均 latency**: 48.2s/chunk
- **平均 tokens/s (output)**: ~32 tokens/s
- **大 chunk (3948 tokens) latency**: 97s — 約為小 chunk 的 2.5 倍
- **最小 chunk (143 tokens) 仍需 30s** — 存在固定開銷（prompt overhead + 模型 output 長度固定約 1000+ tokens）
- **估算全檔 (64 chunks) 耗時**: ~50min（以平均 48s/chunk 推算）

---

## 萃取品質

### Confidence 分布

| 範圍 | 數量 | 說明 |
|------|------|------|
| ≥ 0.90 | 1 | 大段摘要，資訊密度高 |
| 0.80–0.89 | 2 | 地質背景、文獻回顧，專業內容有具體數據 |
| 0.70–0.79 | 2 | 前言、概述，政策性文字，地質細節少 |
| < 0.70 | 0 | — |

### Core 欄位萃取

| 欄位 | Chunk 0 | Chunk 1 | Chunk 2 | Chunk 3 | Chunk 4 |
|------|---------|---------|---------|---------|---------|
| title | 正確 | 正確 | 正確 | 正確 | null |
| institution | 正確 (工研院) | 正確 (地調所) | null | null | null |
| year | 2021 | 2020 | null | null | null |
| abstract | 完整 | 完整 | null | null | null |
| key_findings | 9 條 | 5 條 | 5 條 | 0 條 | 4 條 |
| llm_recommendations | 8 條 | 5 條 | 5 條 | 5 條 | 4 條 |
| llm_commentary | 完整評析 | 完整評析 | 完整評析 | 完整評析 | 完整評析 |

觀察：
- 書目資訊（title, institution, year）主要集中在 Chunk 0-1，後續 chunk 正確回 null
- `llm_commentary` 在所有 chunk 都能產出有意義的專業評析
- `llm_recommendations` 即使在短 chunk 也能根據內容提出合理建議

### Geology Genre 欄位萃取

| 欄位 | Chunk 0 | Chunk 1 | Chunk 2 | Chunk 3 | Chunk 4 |
|------|---------|---------|---------|---------|---------|
| rock_types | 6 種 | [] | [] | 2 種 | [] |
| formations | 3 個 | [] | 2 個 | 7 個 | 1 個 |
| geological_age | 約3 Ma | null | null | 漸新世至更新世 | null |
| well_names | 4 口 | [] | [] | [] | [] |
| exploration_methods | 10 種 | 5 種 | 6 種 | [] | 2 種 |
| geothermal_assessment | 詳細 | null | 簡述 | null | 詳細 (290°C) |

觀察：
- Chunk 0（摘要）資訊最豐富：6 種岩石、4 口井、10 種探勘方法
- Chunk 3（地質背景）成功萃取 7 個地層名稱（五指山層、木山層、大寮層、石底層、南港層、南莊層、桂竹林層）
- Chunk 4（文獻回顧）萃取到關鍵溫度數據：「290°C 侵入體基盤」
- 缺少資訊時正確回 null 或 `[]`，未產生幻覺

---

## Provenance 改善

本次測試使用改善後的 chunker，提供更精確的定位資訊：

```
之前: source_section="(document start)", source_position="heading: (document start)"
之後: source_section="大屯火山群地區", source_position="heading: 大屯火山群地區, p.1, para 0-218"
```

- `source_section`: 自動從第一段落推斷，不再是 placeholder
- `source_position`: 包含 heading + 頁碼範圍 + 段落範圍
- `source_page_end`: 新增欄位，支援跨頁 chunk

已知限制：python-docx 只偵測明確 `<w:br type="page"/>` 分頁符號，無法推算 Word 渲染頁碼。此檔案無明確分頁，故全部顯示 `p.1`。段落索引（para 0-218）是可靠的定位。

---

## 已知問題與改善方向

1. **頁碼不準確** — python-docx 限制，需等 Phase 2 考慮 PDF 來源或其他方案
2. **Chunk 0 過大** — 摘要段 3948 tokens，佔 prompt 主要篇幅，可考慮拆分
3. **重複萃取書目資訊** — 每個 chunk 都重複萃取 title/institution，Phase 2 可做 chunk 合併
4. **全檔耗時長** — 64 chunks × 48s ≈ 50min，Phase 2 需考慮並行或批次處理
5. **Chunk 3 key_findings 為空** — 地質背景段以描述為主，非結論性文字，LLM 判斷無 key findings

---

## 結論

YAML-driven 配置架構在 E2E 測試中表現穩定：

- **萃取品質**: 5/5 chunks 成功解析，平均 confidence 0.848
- **JSON robustness**: `parse_llm_json` 工具成功處理所有 LLM 輸出
- **Genre 專業性**: 地質欄位（岩石、地層、井名、探勘方法）萃取準確，無幻覺
- **配置驅動**: prompt 和 schema 完全由 YAML 控制，無 Python hardcoded 內容

測試結果檔：`output/e2e_test/extraction_results.json`
