# Genre Config Split Plan

## 動機

目前所有 genre 定義內嵌在主 YAML（如 `configs/base.yaml`），隨著 genre 增加，主 YAML 會膨脹。拆分後各 genre 獨立管理，主 config 保持精簡。

## 目標結構

```
configs/
├── base.yaml                   # 唯一主 config（pipeline + LLM + prompts + core schema）
└── genres/
    ├── geology.yaml            # geology genre fields + prompt suffix
    ├── physics.yaml
    └── hydrology.yaml
```

Genre 透過 `base.yaml` 的 `extraction.genre` 切換，不需要 per-domain config。

## Genre YAML 格式

```yaml
# configs/genres/geology.yaml
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
  ...
```

頂層就是 `system_prompt_suffix` + `fields`，不需要再包 genre name key。

## 主 YAML 變化

Before:
```yaml
lmetl:
  extraction:
    genre: geology
  schemas:
    core: { ... }
    genres:
      geology:
        system_prompt_suffix: ...
        fields: [...]
```

After:
```yaml
lmetl:
  extraction:
    genre: geology          # 自動從 configs/genres/geology.yaml 載入
  schemas:
    core: { ... }
    # genres 區塊移除，由 config loader 自動 merge
```

## 載入邏輯（config.py）

`load_lmetl_config()` 在讀完主 YAML 後：

1. 取得 `extraction.genre` 的值（例如 `"geology"`）
2. 計算 genre 路徑：`{config_dir}/genres/{genre}.yaml`
3. 讀取 genre YAML，merge 到 `config["schemas"]["genres"][genre]`
4. 如果主 YAML 已有 inline genre 定義（向後相容），不覆蓋

```python
def load_lmetl_config(config_path: str) -> Dict[str, Any]:
    path = Path(config_path)
    with open(path) as f:
        full_config = yaml.safe_load(f)

    config = _resolve_env_vars(full_config.get("lmetl", {}))

    # Auto-load genre from external file
    genre = config.get("extraction", {}).get("genre")
    if genre:
        genre_file = path.parent / "genres" / f"{genre}.yaml"
        if genre_file.exists():
            genres = config.setdefault("schemas", {}).setdefault("genres", {})
            if genre not in genres:  # 不覆蓋 inline 定義
                with open(genre_file) as f:
                    genres[genre] = yaml.safe_load(f)

    return config
```

## 向後相容

- 如果主 YAML 裡仍有 `schemas.genres.geology` inline 定義 → 優先使用 inline，不讀外部檔案
- 如果 `configs/genres/geology.yaml` 不存在且主 YAML 也沒有 inline 定義 → `SchemaLoader` 回傳空 fields，行為與現在相同

## 受影響元件

| 元件 | 需要改動 | 原因 |
|------|---------|------|
| `config.py` | **是** | 加 genre 自動載入邏輯 |
| `sync_schemas` | **是** | 需讀 genre 外部檔案，或改用 `load_lmetl_config()` |
| `base.yaml` | **是** | 移除 inline genre，保留 core |
| `SchemaLoader` | 否 | 只讀 dict |
| `PromptBuilder` | 否 | 只讀 dict |
| `LLMTransform` | 否 | 透過 `load_lmetl_config()` |
| `run_extraction` | 否 | 透過 `load_lmetl_config()` |
| Unit tests | **部分** | `test_sync_schemas` 需更新（config 結構變了） |

## sync_schemas 調整

兩個選擇：

- **方案 A（推薦）**：`sync_schemas` 改用 `load_lmetl_config()` 讀 merged config，零邏輯改動
- **方案 B**：`sync_schemas` 同時掃描 `configs/genres/*.yaml`，可獨立於主 config 運行

推薦方案 A，保持單一入口。

## 實作步驟

1. 建立 `configs/genres/geology.yaml`，從主 YAML 搬出 geology genre 定義
2. 修改 `config.py` 的 `load_lmetl_config()`，加入 genre 自動載入
3. 修改 `base.yaml`，移除 inline genre 區塊
4. 修改 `sync_schemas` 改用 `load_lmetl_config()`
5. 更新 tests
6. 更新 README genre 範例
7. 跑 tests 驗證
