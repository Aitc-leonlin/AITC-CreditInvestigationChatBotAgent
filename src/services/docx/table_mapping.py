SUBJECT_MAP = {
    "full_name_zhtw": "公司名稱",
}

COMPANY_PROFILE_MAP = {
    "stock_code": "股票代號",
    "full_name_zhtw": "中文全名",
    "short_name_zhtw": "中文簡稱",
    "gui_no": "統一編號",
    "address_zhtw": "中文地址",
    "phone": "電話",
    "fax": "傳真",
    "website": "網站",
    "email": "電子郵件",
    "industry_main": "主要產業",
    "industry_sub": "次產業",
    "industry_national": "行業別",
    "ceo": "負責人",
    "capital": "資本額",
    "employee_count": "員工人數",
    "founded_date": "成立日期",
    "business_scope": "營業項目",
    "accountant_firm": "會計師事務所",
    "accountants": "簽證會計師",
    "board_shareholding_ratio": "董監持股比率",
    "board_pledge_ratio": "董監質押比率",
    "listed_market": "上市櫃市場",
    "par_value": "面額",
    "ipo_date": "上市櫃日期",
    "avg_60d_price": "近60日均價",
    "avg_60d_volume": "近60日均量",
}

COMPANY_EN_PROFILE_MAP = {
    "full_name_enus": "英文全名",
    "short_name_enus": "英文簡稱",
    "address_enus": "英文地址",
}

BALANCE_SHEET_MAP = {
    "year": "年度",
    "quarter": "季度",
    "retained_earnings": "保留盈餘",
    "other_accounts_receivable": "其他應收款",
    "other_current_assets": "其他流動資產",
    "inventory": "存貨",
    "accounts_receivable": "應收帳款",
    "total_equity": "權益總額",
    "current_liabilities": "流動負債",
    "current_assets": "流動資產",
    "cash": "現金及約當現金",
    "capital_stock": "股本",
    "total_liabilities_and_equity": "負債及權益總額",
    "capital_reserve": "資本公積",
    "total_assets": "資產總額",
    "non_current_liabilities": "非流動負債",
    "non_current_assets": "非流動資產",
}

FINANCIAL_RATIOS_MAP = {
    "year": "年度",
    "gui_no": "統一編號",
    "average_collection_period": "平均收現期間",
    "total_asset_turnover": "總資產週轉率",
    "roe": "股東權益報酬率",
    "average_days_sales_outstanding": "平均銷貨收款天數",
    "net_profit_margin": "淨利率",
    "debt_to_asset_ratio": "負債比率",
    "pre_tax_profit_to_capital_ratio": "稅前純益佔資本比率",
    "long_term_capital_to_fixed_assets_ratio": "長期資金佔固定資產比率",
    "current_ratio": "流動比率",
    "interest_coverage_ratio": "利息保障倍數",
    "roa": "資產報酬率",
    "cash_reinvestment_ratio": "現金再投資比率",
    "cash_adequacy_ratio": "現金允當比率",
    "quick_ratio": "速動比率",
    "accounts_receivable_turnover": "應收帳款週轉率",
    "fixed_assets_turnover": "固定資產週轉率",
    "inventory_turnover": "存貨週轉率",
    "cash_flow_ratio": "現金流量比率",
    "eps": "每股盈餘",
}


def label(mapping: dict[str, str], key: str) -> str:
    return mapping.get(key, key)
