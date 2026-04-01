# pwetl 參考分析

- Repo: https://github.com/sw-willie-wu/pwetl.git
- Local clone: `docs/references/project/pwetl/`
- License: MIT
- Version: v0.3.0

## 概述

基於 Pathway streaming engine 的宣告式 ETL 框架，YAML 配置驅動，Plugin 架構。

## 可借鏡的設計

- Plugin 架構：BaseSource / BaseTransform / BaseSink 抽象類別
- Factory + Registry pattern：依 config type 動態建立元件
- YAML 宣告式配置 + Pydantic 驗證
- 三層驗證模式（none / sample / strict）
- 環境變數替換機制（`${VAR:default}`）

## pwetl 不涵蓋的部分（我們需要自建）

- 文獻解析（PDF / HTML / TXT → text chunks）
- LLM 萃取（schema-driven prompting）
- OCR 處理

## 可直接使用的模組

- BaseSource / BaseTransform / BaseSink（繼承擴充）
- FileSource / FileSink（CSV/JSON/JSONL）
- DatabaseSource / DatabaseSink（SQLAlchemy）
- ETLEngine / Pipeline（執行引擎）
- ConfigLoader + YAML 配置機制
- Pydantic 驗證框架（none / sample / strict）

## 決定

**以 pwetl 作為 library 依賴**（`pip install pwetl`），自建文獻 + LLM 擴充模組。
專案定位：pwetl 的下游應用 / 擴充套件。
