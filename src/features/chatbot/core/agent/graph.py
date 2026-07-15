# import LangGraph lib
from langgraph.graph import StateGraph, START, END
from langgraph.graph import MessagesState
from typing_extensions import TypedDict, NotRequired, Annotated

# import langGraph nodes
from src.features.chatbot.core.agent.nodes.rephrase_question import rephrase_question
from src.features.chatbot.core.agent.nodes.classify_is_question_in_range import (
    classify_is_question_in_range,
)
from src.features.chatbot.core.agent.nodes.classify_statement_type import classify_statement_type
from src.features.chatbot.core.agent.nodes.exact_query import exact_query
from src.features.chatbot.core.agent.nodes.extract_semantic_plan_node import extract_semantic_plan_node
from src.features.chatbot.core.agent.nodes.select_applied_expert_knowledge import (
    select_applied_expert_knowledge,
)
from src.features.chatbot.core.agent.nodes.select_applied_warehouse_data import (
    select_applied_warehouse_data,
)
from src.features.chatbot.core.agent.nodes.semantic_retrieval import semantic_retrieval
from src.features.chatbot.core.agent.nodes.use_external_data import use_external_data
from src.features.chatbot.core.agent.nodes.classify_question_type import classify_question_type
from src.features.chatbot.core.agent.nodes.question_out_of_range import question_out_of_range

# import type
from src.features.chatbot.models.langgraph_state_types import OverallState


from langgraph.checkpoint.memory import MemorySaver


# 路徑判斷：根據 classify_question_type 產生的 question_type 決定查詢路線。
# - EXACT_QUERY：使用者要查明確財報欄位/數字，先判斷報表類型再做精確查詢。
# - SEMANTIC / ANALYSIS / DECISION / 其他：進入語意分析路線，先規劃 requirements。
def question_type_condition_edge(state: OverallState) -> str:
    if str(state.get("request_source") or "").strip().lower() == "chatbot-with-external":
        return "semantic_retrieval"
    match state["question_type"]:
        case "EXACT_QUERY":
            return "classify_statement_type"
        case _:
            return "semantic_retrieval"


# 路徑判斷：根據 classify_is_question_in_range 產生的 is_question_in_range 決定是否繼續。
# - "True"：問題屬於財報/授信可處理範圍，繼續判斷問題類型。
# - "False"：問題超出範圍，改由 question_out_of_range 產生固定回覆後結束。
# - 其他值：防呆，直接結束。
def is_question_in_range_edge(state: OverallState) -> str:
    try:
        # print("is_question_in_range_edge in========", state["is_question_in_range"])
        match state["is_question_in_range"]:
            case "True":
                return "classify_question_type"
            case "False":
                return "question_out_of_range"
            case _:
                return "END"
    except (ValueError, TypeError) as e:
        print(f"發生錯誤: {e}")


# 路徑判斷：use_external_data 判斷 requirements purpose 後，決定是否提前回前端確認。
# - awaiting_external_data_confirmation = True：
#   LLM 判斷需要外部資料，且已產生 external_data_query_text，流程先結束讓前端確認。
# - False：不需要外查或已處理完外部資料狀態，繼續執行專家知識與資料倉儲節點。
def external_data_condition_edge(state: OverallState) -> str:
    if bool(state.get("awaiting_external_data_confirmation")):
        return "END"
    return "select_applied_expert_knowledge"


# 路徑判斷：extract_semantic_plan_node 產生 requirements 後，是否先啟動外部資料需求判斷線。
# - use_external_data = True：
#   執行 use_external_data node，讓 LLM 根據 requirements[].purpose 判斷是否需要外部資料。
# - use_external_data = False：
#   跳過 use_external_data node，直接進入正常專家知識與資料倉儲節點。
# use_warehouse_data 只控制是否套用前端傳入的 appliedWarehouseData。
# 注意：use_external_data 必須在 select_applied_expert_knowledge / select_applied_warehouse_data 前面，
# 避免 LLM 已判斷需要回前端確認時，後續知識節點被提前重複執行。
def should_judge_external_data_edge(state: OverallState) -> str:
    if bool(state.get("use_external_data", True)):
        return "use_external_data"
    return "select_applied_expert_knowledge"


# 宣告Graph Workflow
workflow = StateGraph(OverallState)

# 宣告 LangGraph Node 與各節點職責：
# - rephrase_question：依照對話歷史重寫問題，讓後續節點拿到可獨立理解的查詢文字。
workflow.add_node(rephrase_question)
# - classify_is_question_in_range：判斷問題是否屬於財報/授信系統處理範圍。
workflow.add_node(classify_is_question_in_range)
# - classify_question_type：分類問題為 EXACT_QUERY、SEMANTIC、ANALYSIS 或 DECISION。
workflow.add_node(classify_question_type)
# - classify_statement_type：精確查詢路線使用，判斷欄位屬於資產負債表、綜合損益表或現金流量表。
workflow.add_node(classify_statement_type)
# - exact_query：精確查詢路線使用，解析公司/期間/欄位後查資料庫並產生答案。
workflow.add_node(exact_query)
# - extract_semantic_plan_node：語意分析路線使用，規劃需要查哪些 requirements 與各 requirement 的 purpose。
workflow.add_node(extract_semantic_plan_node)
# - use_external_data：根據 requirements[].purpose 判斷是否需要外部資料，必要時產生 external_data_query_text 給前端確認。
workflow.add_node(use_external_data)
# - select_applied_expert_knowledge：根據前端傳入的 appliedExpertKnowledge 選出本題要套用的專家知識。
workflow.add_node(select_applied_expert_knowledge)
# - select_applied_warehouse_data：固定執行；節點內根據 useWarehouseData 決定是否套用前端傳入的 appliedWarehouseData。
workflow.add_node(select_applied_warehouse_data)
# - semantic_retrieval：依 semantic plan 查財報資料，整合專家知識/資料倉儲/外部資料後產生分析回答。
workflow.add_node(semantic_retrieval)
# - question_out_of_range：問題超出處理範圍時產生回覆。
workflow.add_node(question_out_of_range)

# 宣告 LangGraph Edge：
# START 後先重寫問題，避免多輪對話中的代名詞或省略內容影響分類。
workflow.add_edge(START, "rephrase_question")

# 重寫完成後，先判斷是否屬於系統處理範圍。
workflow.add_edge("rephrase_question", "classify_is_question_in_range")
workflow.add_conditional_edges(
    source="classify_is_question_in_range",
    path=is_question_in_range_edge,
    path_map={
        "classify_question_type": "classify_question_type",
        "question_out_of_range": "question_out_of_range",
    },
)
workflow.add_edge("question_out_of_range", END)

# 範圍內問題再判斷查詢型態：精確數字查詢走 exact_query，其餘走 semantic analysis。
workflow.add_conditional_edges(
    source="classify_question_type",
    path=question_type_condition_edge,
    path_map={
        "semantic_retrieval": "extract_semantic_plan_node",
        "classify_statement_type": "classify_statement_type",
    },
)

# 精確查詢路線：先判斷報表類型，再查資料庫，產生答案後結束。
workflow.add_edge("classify_statement_type", "exact_query")
workflow.add_edge("exact_query", END)

# 語意分析路線：先規劃 requirements，再依 useExternalData 決定是否先判斷外部資料需求。
# 若 LLM 判斷需要外部資料，本輪會直接 END，回 externalDataQueryText 給前端確認；
# 若不需要外部資料，才繼續執行專家知識與資料倉儲節點。
workflow.add_conditional_edges(
    source="extract_semantic_plan_node",
    path=should_judge_external_data_edge,
    path_map={
        "use_external_data": "use_external_data",
        "select_applied_expert_knowledge": "select_applied_expert_knowledge",
    },
)

# 外部資料需求判斷後，若需要前端確認 externalDataQueryText 就先結束；
# 否則回到正常流程，繼續執行專家知識與資料倉儲節點。
workflow.add_conditional_edges(
    source="use_external_data",
    path=external_data_condition_edge,
    path_map={
        "END": END,
        "select_applied_expert_knowledge": "select_applied_expert_knowledge",
    },
)

# SEMANTIC 正常流程：先選專家知識，再執行資料倉儲節點。
workflow.add_edge("select_applied_expert_knowledge", "select_applied_warehouse_data")
workflow.add_edge("select_applied_warehouse_data", "semantic_retrieval")

# 語意檢索節點產生最終分析答案後結束。
workflow.add_edge("semantic_retrieval", END)

# Add simple in-memory checkpointer
# memory = MemorySaver()
# graph = workflow.compile(checkpointer=memory)
graph = workflow.compile()
