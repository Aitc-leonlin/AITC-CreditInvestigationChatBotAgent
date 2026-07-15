import json
from time import perf_counter

from src.features.chatbot.models.langgraph_state_types import OverallState


def select_applied_warehouse_data(state: OverallState) -> OverallState:
    started_at = perf_counter()
    if not bool(state.get("use_warehouse_data", True)):
        print("[select_applied_warehouse_data] skipped: use_warehouse_data is false")
        return {
            **state,
            "needs_warehouse_data": False,
            "selected_applied_warehouse_data": [],
            "warehouse_data_selection_result": {
                "needs_warehouse_data": False,
                "selected_indexes": [],
                "reason": "Skipped because referenceSettings.useWarehouseData is false.",
            },
        }

    warehouse_data_items = state.get("applied_warehouse_data") or []

    if not warehouse_data_items:
        print("[select_applied_warehouse_data] no applied warehouse data provided")
        return {
            **state,
            "needs_warehouse_data": False,
            "selected_applied_warehouse_data": [],
            "warehouse_data_selection_result": {
                "needs_warehouse_data": False,
                "selected_indexes": [],
                "reason": "No appliedWarehouseData provided.",
            },
        }

    selected_indexes = list(range(1, len(warehouse_data_items) + 1))
    selection_result = {
        "needs_warehouse_data": True,
        "selected_indexes": selected_indexes,
        "reason": "Forward all appliedWarehouseData items from the frontend to the final prompt without filtering.",
    }

    print(
        "[select_applied_warehouse_data] passthrough items:\n"
        + json.dumps(warehouse_data_items, ensure_ascii=False, indent=2)
    )
    print(
        "[select_applied_warehouse_data] result:\n"
        + json.dumps(selection_result, ensure_ascii=False, indent=2)
    )
    print(
        f"[timing] select_applied_warehouse_data took {perf_counter() - started_at:.3f}s"
    )

    return {
        **state,
        "needs_warehouse_data": True,
        "selected_applied_warehouse_data": warehouse_data_items,
        "warehouse_data_selection_result": selection_result,
    }
