# Directory Convention

## Documentation (`./docs/`)

All documentation must be organized by purpose, then by module:

```
docs/
├── plans/          # 規劃文件
│   ├── etl/
│   ├── llm/
│   └── project/
└── references/     # 參考資料
    ├── etl/
    ├── llm/
    └── project/
```

- New doc categories follow the same pattern: `docs/{category}/{module}/`
- Each module folder mirrors the project's module structure

## Rules (`./claude/rules/`)

```
.claude/
├── CLAUDE.md
└── rules/
    ├── etl/        # ETL pipeline rules
    ├── llm/        # LLM provider rules
    └── project/    # Project-level conventions
```

## General Principle

All organized directories (docs, rules, etc.) must subdivide by module. Never dump files flat at the category root — always place them under the appropriate module folder.
