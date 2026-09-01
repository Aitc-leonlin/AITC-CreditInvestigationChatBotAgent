# XBRL 財報匯入簡易操作

這份文件只說明兩件事：

1. 第一次建立資料庫
2. 將公司 XBRL／iXBRL 財務報表匯入資料庫

以下指令都必須在後端專案根目錄執行：

```bash
cd "/Users/leonlin/Cursor/BackEnd/AITC-CreditInvestigationChatBotAgent"
```

## 一、第一次安裝環境

第一次使用時執行：

```bash
make setup
mkdir -p output
```

如果專案已經有 `venv`，可以跳過 `make setup`。

## 二、第一次建立資料庫

如果專案根目錄已經有可使用的 `FinancialStatementXBRL.db`，請直接跳到下一節。

建立新 DB 與 XBRL TABLE：

```bash
venv/bin/python -c "import sqlite3; from pathlib import Path; con=sqlite3.connect('FinancialStatementXBRL.db'); con.executescript(Path('src/sql/migrations/sqlite/V1.0__initialize_financial_statement_xbrl_schema.sql').read_text(encoding='utf-8')); con.commit(); con.close(); print('DB 初始化完成')"
```

這一步只建立 TABLE，還沒有匯入 XBRL Criteria 與公司財報。

## 三、第一次匯入公司財報

第一次匯入時，必須同時指定：

- XBRL Criteria 資料夾
- 公司財報 XBRL／HTML 檔案
- 要寫入的 DB
- SQL 輸出位置

把下面兩個 `/path/to/...` 換成實際路徑：

```bash
venv/bin/python scripts/build_xbrl_sql.py \
  --taxonomy-root "/path/to/XBRL Criteria tifrs-20200630" \
  --instance "/path/to/company-report.html" \
  --db-path FinancialStatementXBRL.db \
  --sql-output output/first_report_import.sql
```

完成後會同時：

- 將 XBRL Criteria、公司財報與財務數值寫入 `FinancialStatementXBRL.db`
- 保留一份匯入 SQL：`output/first_report_import.sql`

## 四、之後匯入其他公司財報

DB 已有 Taxonomy 資料後，不需要再讀一次 Criteria，改用 `--taxonomy-from-db`。

匯入單一財報：

```bash
venv/bin/python scripts/build_xbrl_sql.py \
  --taxonomy-from-db \
  --db-path FinancialStatementXBRL.db \
  --instance "/path/to/company-report.html" \
  --sql-output output/company_report_import.sql
```

一次匯入資料夾內的全部財報：

```bash
venv/bin/python scripts/build_xbrl_sql.py \
  --taxonomy-from-db \
  --db-path FinancialStatementXBRL.db \
  --instance-dir "/path/to/financial-report-folder" \
  --sql-output output/company_reports_import.sql
```

支援的財報副檔名：`.xbrl`、`.xml`、`.html`、`.htm`。

## 五、確認是否匯入成功

查看最近匯入的財報：

```bash
venv/bin/python -c "import sqlite3; con=sqlite3.connect('FinancialStatementXBRL.db'); print(con.execute('SELECT company_code, year, quarter, file_name FROM report_instance ORDER BY rowid DESC LIMIT 10').fetchall()); con.close()"
```

看到公司代號、年度、季度與檔名，代表財報主檔已寫入 DB。

也可以確認主要資料筆數：

```bash
venv/bin/python -c "import sqlite3; con=sqlite3.connect('FinancialStatementXBRL.db'); print('report_instance:', con.execute('SELECT COUNT(*) FROM report_instance').fetchone()[0]); print('xbrl_fact:', con.execute('SELECT COUNT(*) FROM xbrl_fact').fetchone()[0]); print('financial_metric_value:', con.execute('SELECT COUNT(*) FROM financial_metric_value').fetchone()[0]); con.close()"
```

## 六、重要提醒

- 請先備份正式 DB，再進行大量匯入。
- 不要重複匯入同一份財報，否則 `financial_metric_value` 可能產生重複資料。
- `--db-path` 不可省略；省略時只會產生 SQL，不會寫入 DB。
- `--taxonomy-root` 只在 DB 第一次建立 Taxonomy 時使用。後續匯入請用 `--taxonomy-from-db`。
- SQL 成功產生不一定代表 DB 已寫入，請用第五節的查詢再次確認。

## 七、啟動後端

資料匯入完成後，可啟動後端：

```bash
make run
```
