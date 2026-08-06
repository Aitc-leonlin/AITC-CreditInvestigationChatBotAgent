# CreditInvestigationChatBotPython

This project is a backend server for a Credit Investigation ChatBot, implemented in Python 3.

## Setup

1. **Install dependencies:**
   ```bash
   make setup
   ```

2. **Run the server:**
   ```bash
   make start
    ```

If you want a single command similar to `package.json` scripts, use the included `Makefile`. `make start` will create `venv`, install `requirements.txt`, then run `app.py`. If dependencies are already installed and you only want to start the app, use `make run`.

## LLM Provider

The backend uses `src/features/chatbot/core/providers/chat_openAI_provider.py` as the shared chat model provider. Existing behavior remains OpenAI by default:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL_NAME=gpt-5-mini
```

To use an OpenAI-compatible local LLM server, switch only the environment variables:

```bash
LLM_PROVIDER=local
LOCAL_LLM_BASE_URL=http://192.168.20.169:8004/v1
LOCAL_LLM_MODEL_NAME=JunHowie/Qwen3-30B-A3B-Instruct-2507-GPTQ-Int4
LOCAL_LLM_API_KEY=not-needed
```

`LOCAL_LLM_BASE_URL` may also be set to a full chat completions endpoint such as `http://192.168.20.169:8004/v1/chat/completions`; the provider normalizes it to the `/v1` base URL required by LangChain.

## Regression Tests

Run the backend regression suite with:

```bash
make test-regression
```

The runner first prints the current FastAPI API feature inventory, then executes contract and CRUD checks. It copies `FinancialStatementXBRL.db` to a temporary SQLite file and sets `SQLITE_DB_PATH` to that copy, so test writes do not modify the project database.

To only list the current API features:

```bash
venv/bin/python scripts/run_regression_tests.py --list-only
```

The default suite avoids successful chatbot/report generation calls because those paths may invoke an external or local LLM. It still verifies protected chatbot auth behavior and local LLM provider URL normalization.

## Project Structure
- `app.py`: Main entry point for the backend server.
- `requirements.txt`: Python dependencies.

## Backend Modules

Backend feature code is organized under `src/features`. Each module owns the API entry points, business logic, schemas, and module-specific utilities for one business domain.

Current modules:

- `src/features/chatbot`: Chatbot APIs, expert-knowledge APIs, warehouse-data APIs, LangGraph agent flow, LLM provider, XBRL mapping resources, and chatbot-specific helper services.
- `src/features/membership`: Membership, authentication, RBAC, menu permissions, organization, audit, notification, and admin APIs.
- `src/features/report_generator`: Credit report generation APIs, report history/dashboard logic, LLM conclusion service, and DOCX chapter generation services.

Common module folders:

| Folder | Purpose |
|---|---|
| `api` | FastAPI routers and endpoints. This is the HTTP entry layer called by frontend clients. |
| `schemas` | Pydantic request/response models and API validation shapes. These also affect Swagger/OpenAPI documentation. |
| `services` | Business logic and workflow orchestration. API handlers should delegate main behavior here. |
| `repositories` | Database access logic such as queries, inserts, updates, deletes, and row mapping. |
| `models` | Domain/data models used by the module, including database entities or workflow state types. |
| `core` | Module-specific shared utilities and lower-level building blocks, such as auth helpers, JWT/password utilities, LangGraph agent code, providers, or mappings. |
| `seeds` | Default seed data used during bootstrap, currently mainly used by membership. |
| `validation` | Shared validation helpers inside a module, currently mainly used by membership. |

Cross-module utilities should go under `src/shared` instead of inside one module. For example, shared database path utilities are under `src/shared/database`.

Placement rules for future changes:

- New API route: `src/features/<module>/api`
- New business workflow/service: `src/features/<module>/services`
- New DB access code: `src/features/<module>/repositories`
- New request/response schema: `src/features/<module>/schemas`
- New module-only helper: `src/features/<module>/core`
- Utility used by multiple modules: `src/shared`

## XBRL To SQL

Use `scripts/build_xbrl_sql.py` to parse a `tifrs-20200630` taxonomy directory together with one XBRL instance file, then generate SQL `INSERT` statements for these tables:

- `report_instance`
- `taxonomy_entry_point`
- `taxonomy_concept`
- `taxonomy_presentation`
- `taxonomy_calculation`
- `xbrl_fact`
- `field_dictionary`
- `field_concept_mapping`
- `financial_metric_value`

Example:

```bash
python3 scripts/build_xbrl_sql.py \
  --taxonomy-root /path/to/tifrs-20200630 \
  --instance /path/to/report.xbrl \
  --sql-output ./output/report_import.sql
```

## 財務報表解析匯入流程

如果要把下載好的財務報表 XBRL/iXBRL 檔案匯入 `FinancialStatementXBRL.db`，主要使用 `scripts/build_xbrl_sql.py`。這個 script 會解析財報檔案，並寫入 `report_instance`、`xbrl_fact`、`financial_metric_value` 等查詢報告會用到的資料表。

### 1. 準備財報檔案

把同一批要匯入的財報放在同一個資料夾中，支援副檔名：

- `.xbrl`
- `.xml`
- `.html`
- `.htm`

檔名建議維持公開資訊觀測站下載格式，例如：

```text
tifrs-fr1-m1-ci-cr-4960-2025Q1.html
tifrs-fr1-m1-ci-cr-4960-2025Q2.html
tifrs-fr1-m1-ci-cr-4960-2025Q3.html
tifrs-fr1-m1-ci-cr-4960-2025Q4.html
```

### 2. 使用既有 DB taxonomy 匯入財報

如果 `FinancialStatementXBRL.db` 已經有 taxonomy 資料，使用 `--taxonomy-from-db` 即可，不需要重新解析 taxonomy 目錄。

```bash
python3 scripts/build_xbrl_sql.py \
  --taxonomy-from-db \
  --db-path FinancialStatementXBRL.db \
  --instance-dir /path/to/financial-report-folder \
  --sql-output ./output/import_financial_reports.sql
```

這個指令會做兩件事：

- 產生 SQL 檔到 `--sql-output`
- 因為有帶 `--db-path`，會直接把 SQL 載入 `FinancialStatementXBRL.db`

匯入後會影響的主要資料表：

- `report_instance`: 每一份財報的基本資料，例如公司代碼、年度、季度、檔名、期間。
- `xbrl_fact`: 財報裡每一個 XBRL 科目的實際數值或文字，例如營收、淨利、資產、負債。
- `financial_metric_value`: 依照目前 mapping 建出的查詢用指標值，報告產生與趨勢圖會用到。

### 3. 只解析單一財報檔案

如果只要匯入一個檔案，用 `--instance`：

```bash
python3 scripts/build_xbrl_sql.py \
  --taxonomy-from-db \
  --db-path FinancialStatementXBRL.db \
  --instance /path/to/tifrs-fr1-m1-ci-cr-4960-2025Q1.html \
  --sql-output ./output/import_4960_2025Q1.sql
```

### 4. 第一次建立 taxonomy 資料

如果 DB 還沒有 taxonomy，才需要用 `--taxonomy-root` 指向 taxonomy 目錄。這會把 taxonomy metadata 與財報一起產生 SQL。

```bash
python3 scripts/build_xbrl_sql.py \
  --taxonomy-root /path/to/tifrs-20200630 \
  --instance-dir /path/to/financial-report-folder \
  --db-path FinancialStatementXBRL.db \
  --sql-output ./output/import_with_taxonomy.sql
```

### 5. 匯入後檢查

確認 `report_instance` 是否有進資料：

```bash
python3 -c "import sqlite3; con=sqlite3.connect('FinancialStatementXBRL.db'); print(con.execute(\"select report_id, company_code, year, quarter from report_instance where company_code='4960' order by year, quarter\").fetchall()); con.close()"
```

確認每季 `xbrl_fact` 筆數：

```bash
python3 -c "import sqlite3; con=sqlite3.connect('FinancialStatementXBRL.db'); print(con.execute(\"select ri.quarter, count(xf.fact_id) from report_instance ri left join xbrl_fact xf on xf.report_id=ri.report_id where ri.company_code='4960' and ri.year=2025 group by ri.quarter order by ri.quarter\").fetchall()); con.close()"
```

確認 `financial_metric_value` 筆數：

```bash
python3 -c "import sqlite3; con=sqlite3.connect('FinancialStatementXBRL.db'); print(con.execute(\"select quarter, count(*) from financial_metric_value where company_code='4960' and year=2025 group by quarter order by quarter\").fetchall()); con.close()"
```

### 6. 其他 XBRL 維護 scripts

- `scripts/parse_xbrl_dictionary.py`: 解析 XBRL dictionary，產出完整的 account title 資料。
- `scripts/split_xbrl_dictionary.py`: 將完整 dictionary 拆成資產負債表、綜合損益表、現金流量表等較小檔案。
- `scripts/build_xbrl_mapping_json.py`: 依 dictionary 建立 concept mapping JSON，供欄位對應與查詢使用。
- `scripts/build_xbrl_sql.py`: 實際匯入財務報表時最主要使用的 script。

If you only want taxonomy SQL first, `--instance` is optional:

```bash
python3 scripts/build_xbrl_sql.py \
  --taxonomy-root /path/to/tifrs-20200630 \
  --sql-output ./output/taxonomy_only.sql
```

By default, `field_dictionary` and `field_concept_mapping` are created in `auto-concept` mode, which means each parsed concept is mapped 1:1 to an internal field. If you already have your own business field definitions, switch to `--field-mode custom` and provide a JSON file shaped like:

```json
{
  "fields": [
    {
      "field_id": "assets",
      "canonical_name": "assets",
      "zh_name": "資產總額",
      "en_name": "Assets",
      "module": "BSCI",
      "statement_type": "balance_sheet",
      "value_type": "numeric",
      "description": "Total assets"
    }
  ],
  "mappings": [
    {
      "field_id": "assets",
      "taxonomy_id": "tifrs-20200630:BSCI",
      "concept_ids": ["ifrs-full_Assets"],
      "industry_type": "CI",
      "priority": 1,
      "effective_from": "2020-06-30",
      "effective_to": null
    }
  ]
}
```
