from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from src.providers.chat_openAI_provider import chat_model
from src.types.langgraph_state_types import OverallState


class InputState(TypedDict):
    user_input: str


class QueryTypeSchema(BaseModel):
    query_type: Literal["EXACT_QUERY", "SEMANTIC", "ANALYSIS", "DECISION"] = Field(
        description="使用者問題的主要類型"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="模型對本次分類結果的信心分數，介於 0 到 1 之間",
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


def classify_question_type(state: OverallState):
    started_at = perf_counter()
    question = state.get("rephrased_question") or state.get("user_input") or ""
    sanitized_question = sanitize_llm_text(question)

    structured_llm = chat_model.with_structured_output(QueryTypeSchema)
    classify_question_type_prompt = f"""
You are an intent classifier for a financial statement AI system.

Classify the user's question into exactly one type:
- EXACT_QUERY: asks for a specific metric, value, amount, ratio, or a single clearly defined field for a company and period.
- SEMANTIC: asks about meaning, definition, interpretation, or broad retrieval of financial information without requiring a judgment or recommendation.
- ANALYSIS: asks for explanation, trend analysis, performance review, risk analysis, comparison, or reasoning that combines multiple financial facts.
- DECISION: asks whether something is good/bad, safe/unsafe, should/should not, invest/not invest, or requests a recommendation / final judgment.

Rules:
- Return exactly one query_type from: EXACT_QUERY, SEMANTIC, ANALYSIS, DECISION.
- Return a confidence score between 0 and 1.
- If the question asks for a direct value, prefer EXACT_QUERY.
- If the question asks "how to interpret" or "what does X mean", prefer SEMANTIC.
- If the question asks for analytical reasoning based on multiple data points, prefer ANALYSIS.
- If the question asks for a recommendation, conclusion, or go/no-go judgment, prefer DECISION.

Examples:
Q: 請給我台泥2024年Q1的收取之股利
A: {{"query_type": "EXACT_QUERY", "confidence": 0.96}}

Q: 請解釋什麼是營運資金
A: {{"query_type": "SEMANTIC", "confidence": 0.88}}

Q: 1503這家公司2024年負債結構是否有風險
A: {{"query_type": "ANALYSIS", "confidence": 0.82}}

Q: 這家公司目前適不適合投資
A: {{"query_type": "DECISION", "confidence": 0.73}}

User question:
{sanitized_question}
"""

    # print("[classify_question_type] prompt:\n" + classify_question_type_prompt)
    result = structured_llm.invoke(classify_question_type_prompt)
    classification = result.model_dump()

    print("[classify_question_type] result:", classification)
    print(f"[timing] classify_question_type took {perf_counter() - started_at:.3f}s")

    return {
        **state,
        "question_type": classification["query_type"],
        "question_type_confidence": classification["confidence"],
        "question_type_result": classification,
    }
