import json
from time import perf_counter

from src.features.chatbot.core.agent.nodes.semantic_retrieval import extract_semantic_plan
from src.features.chatbot.models.langgraph_state_types import OverallState


def extract_semantic_plan_node(state: OverallState) -> OverallState:
    started_at = perf_counter()
    question = state.get("rephrased_question") or state.get("user_input") or ""

    try:
        plan = extract_semantic_plan(question)
        print(
            f"[timing] extract_semantic_plan_node.extract_semantic_plan took "
            f"{perf_counter() - started_at:.3f}s"
        )
    except Exception as exc:
        return {
            **state,
            "semantic_plan_error": str(exc),
            "semantic_plan": {},
        }

    print("\n********** [extract_semantic_plan_node] AI AGENT data-requirement plan start **********")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    print("********** [extract_semantic_plan_node] AI AGENT data-requirement plan end **********\n")

    return {
        **state,
        "semantic_plan": plan,
    }
