from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field

from src.providers.chat_openAI_provider import chat_model
from src.types.langgraph_state_types import OverallState


VALID_STATEMENT_TYPES = (
    "balance_sheet",
    "comprehensive_income_statement",
    "statement_of_cash_flows",
)


class StatementFieldClassification(BaseModel):
    field_name: str = Field(description="使用者問題中拆出的單一查詢欄位")
    statement_types: list[
        Literal[
            "balance_sheet",
            "comprehensive_income_statement",
            "statement_of_cash_flows",
        ]
    ] = Field(
        default_factory=list,
        description="該欄位可能對應的報表類型，可複選",
    )
    primary_statement_type: Literal[
        "balance_sheet",
        "comprehensive_income_statement",
        "statement_of_cash_flows",
    ] = Field(description="最優先嘗試查詢的報表類型")


class StatementTypeClassification(BaseModel):
    statement_types: list[
        Literal[
            "balance_sheet",
            "comprehensive_income_statement",
            "statement_of_cash_flows",
        ]
    ] = Field(
        default_factory=list,
        description="整體問題需要跨哪些報表取數，可複選且不得重複",
    )
    field_mappings: list[StatementFieldClassification] = Field(
        default_factory=list,
        description="每個查詢欄位對應的報表分類結果",
    )


def sanitize_llm_text(text: str) -> str:
    if not text:
        return ""
    sanitized_chars = []
    for char in str(text):
        codepoint = ord(char)
        if 0xD800 <= codepoint <= 0xDFFF:
            continue
        if char in "\n\r\t" or codepoint >= 32:
            sanitized_chars.append(char)
    return "".join(sanitized_chars)


def classify_statement_type(state: OverallState) -> OverallState:
    started_at = perf_counter()
    question = state.get("rephrased_question") or state.get("user_input") or ""
    sanitized_question = sanitize_llm_text(question)

    structured_llm = chat_model.with_structured_output(StatementTypeClassification)
    prompt = f"""
你是財報欄位分類器。
請分析使用者問題中提到的所有查詢欄位，判斷每個欄位最可能出現在哪些財務報表，並且支援跨表情境。

可使用的報表類型只有：
- balance_sheet
- comprehensive_income_statement
- statement_of_cash_flows

判斷原則：
1. 問題裡如果一次詢問多個欄位，必須逐一拆開判斷，不可只給整題一個單一報表。
2. 同一欄位若在實務上可能跨表出現，可以回傳多個 statement_types，但仍必須指定一個 primary_statement_type。
3. 整體的 statement_types 應該是所有 field_mappings 內報表類型的去重聯集。
4. 資產、負債、權益、應收款、無形資產、現金及約當現金等期末存量項目，通常屬於 balance_sheet。
5. 收入、成本、費損、獲利等期間經營成果項目，通常屬於 comprehensive_income_statement。
6. 現金流入流出、折舊攤銷調整、收取股利、投資活動、籌資活動等現金移動項目，通常屬於 statement_of_cash_flows。
7. 如果問題提到的欄位像「現金及約當現金」，雖然常見於資產負債表，但若題意是在跨表整批取數，也可將 statement_of_cash_flows 一併列入候選。
8. 只輸出結構化結果，不要輸出說明文字。

範例：
問題：請給我台泥1101的2024年Q1的現金及約當現金、其他應收款、無形資產、長期應收融資租賃款淨額
可接受的分類方向：
- 現金及約當現金 -> ["balance_sheet", "statement_of_cash_flows"]
- 其他應收款 -> ["balance_sheet"]
- 無形資產 -> ["balance_sheet"]
- 長期應收融資租賃款淨額 -> ["balance_sheet"]

使用者問題：
{sanitized_question}
"""

    print("[classify_statement_type] prompt:\n" + prompt)
    result = structured_llm.invoke(prompt)
    classification = result.model_dump()

    field_mappings = classification.get("field_mappings", [])
    overall_statement_types = classification.get("statement_types", [])
    primary_statement_type = (
        field_mappings[0]["primary_statement_type"]
        if field_mappings
        else (overall_statement_types[0] if overall_statement_types else "")
    )

    print("[classify_statement_type] result:", classification)
    print(f"[timing] classify_statement_type took {perf_counter() - started_at:.3f}s")

    return {
        **state,
        "statement_type": primary_statement_type,
        "statement_types": overall_statement_types,
        "statement_type_result": classification,
    }
