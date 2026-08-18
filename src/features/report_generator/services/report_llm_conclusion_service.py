import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.features.chatbot.core.providers.chat_openAI_provider import chat_model, get_message_text
from src.shared.database.db_path import PROJECT_ROOT
from src.shared.database.serialization import database_json_dumps


EVALUATION_RULE_PROMPT_PATH = PROJECT_ROOT / "system-prompts" / "EvaluationRulePrompt.json"
OUT_OF_SCOPE_MESSAGE = "Sorry, the question is Out of my service area."


def load_evaluation_rules() -> dict[str, str]:
    with EVALUATION_RULE_PROMPT_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def compact_ratio_data(ratio_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "debt_to_asset_ratio": ratio_row.get("debt_to_asset_ratio"),
        "current_ratio": ratio_row.get("current_ratio"),
        "quick_ratio": ratio_row.get("quick_ratio"),
        "roa": ratio_row.get("roa"),
        "roe": ratio_row.get("roe"),
        "accounts_receivable_turnover": ratio_row.get("accounts_receivable_turnover"),
        "inventory_turnover": ratio_row.get("inventory_turnover"),
        "total_asset_turnover": ratio_row.get("total_asset_turnover"),
    }


def has_required_ratio_data(ratio_data: dict[str, Any]) -> bool:
    return any(value is not None and value != "" for value in ratio_data.values())


def build_generating_answer_prompt(ratio_data: dict[str, Any]) -> str:
    rules = load_evaluation_rules()
    ratio_data_text = database_json_dumps(ratio_data, ensure_ascii=False, indent=2)
    return (
        "If LLM cannot find the related data in the database, respond "
        f"`{OUT_OF_SCOPE_MESSAGE}` else "
        "answer the following user question, corresponding the given SQL data.\n"
        "Question: Please establish two comments. "
        "First one use source of debt_to_asset_ratio, current_ratio, quick_ratio, roa and roe "
        f"in the {ratio_data_text} and only following rules. "
        "Adding % mark after numerical value on first comment. "
        "The second one use source of accounts_receivable_turnover, inventory_turnover, total_asset_turnover "
        f"in the {ratio_data_text} and only following rules. "
        "Don't Add % mark after numerical value on second comment. "
        "Rules:"
        f"debt_to_asset_ratio: {rules['debt_to_asset_ratio_rule']}"
        f"current_ratio_rule: {rules['current_ratio_rule']}"
        f"quick_ratio_rule: {rules['quick_ratio_rule']}"
        f"roa_rule: {rules['roa_rule']}"
        f"roe_rule: {rules['roe_rule']}"
        f"accounts_receivable_turnover_rule: {rules['accounts_receivable_turnover_rule']}"
        f"inventory_turnover_rule: {rules['inventory_turnover_rule']}"
        f"total_asset_turnover_rule: {rules['total_asset_turnover_rule']}"
    )


def generate_report_llm_conclusion(ratio_row: dict[str, Any]) -> str:
    ratio_data = compact_ratio_data(ratio_row)
    if not has_required_ratio_data(ratio_data):
        return OUT_OF_SCOPE_MESSAGE

    prompt = build_generating_answer_prompt(ratio_data)
    response = chat_model.invoke(
        [
            SystemMessage(
                content=(
                    "You are a credit investigation financial analyst. "
                    "Use only the provided SQL data and rules. "
                    "Return exactly two labeled paragraphs"
                    "And Return the result in Traditional Chinese. "
                )
            ),
            HumanMessage(content=prompt),
        ]
    )
    return get_message_text(response)
