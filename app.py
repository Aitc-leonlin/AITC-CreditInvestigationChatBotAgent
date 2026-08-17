import os
import sys
import asyncio
from contextlib import suppress
import json
import logging
from time import perf_counter
from typing import List

# import chromadb
import uvicorn

from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv

load_dotenv()

# from src.features.chatbot.services.save_document_into_vectordb_service import establish_vector_data
from src.features.chatbot.core.mappings.company_stock_code_array import CompanyStockCodeArray
from fastapi.middleware.cors import CORSMiddleware

# import LangChain lib
from langchain_community.utilities import SQLDatabase
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

# import type
from src.features.chatbot.models.langgraph_state_types import OverallState

# import graph
from src.features.chatbot.core.agent.graph import graph
from src.shared.database.db_path import build_database_diagnostics

# import api routers
from src.features.chatbot.api.chatbot import chatbot_router
from src.features.chatbot.api.chatbot_with_external import chatbot_with_external_router
from src.features.chatbot.api.conversation_history import conversation_history_router
from src.features.report_generator.api.report_generator import report_generator_router
from src.features.chatbot.api.warehouse_data import warehouse_data_router
from src.features.chatbot.api.expert_knowledge import (
    expert_knowledge_analysis_router,
    expert_knowledge_anchor_router,
    expert_knowledge_entries_router,
)
from src.features.membership.api.system_controller import membership_system_router
from src.features.membership.api.auth_controller import membership_auth_router
from src.features.membership.api.menu_controller import menu_router
from src.features.membership.api.rbac_controller import rbac_router
from src.features.membership.api.user_controller import membership_user_router
from src.features.membership.api.organization_controller import organization_router
from src.features.membership.api.notification_controller import membership_admin_router
from src.features.membership.api.group_controller import group_router
from src.features.membership.core.exceptions import MembershipError, membership_error_handler
from src.features.membership.core.audit_middleware import audit_http_middleware
from src.features.membership.services.audit_retention_service import run_audit_retention_scheduler
from src.features.membership.services.bootstrap_service import ensure_membership_infrastructure


from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage


# 要開啟python專案時，都要下這個指令開啟該專案的虛擬環境
# python3 -m venv venv
# source venv/bin/activate


app = FastAPI()
app.middleware("http")(audit_http_middleware)
api_router = APIRouter()
api_router.include_router(chatbot_router)
api_router.include_router(chatbot_with_external_router)
api_router.include_router(conversation_history_router)
api_router.include_router(report_generator_router)
api_router.include_router(warehouse_data_router)
api_router.include_router(expert_knowledge_entries_router)
api_router.include_router(expert_knowledge_anchor_router)
api_router.include_router(expert_knowledge_analysis_router)
api_router.include_router(membership_system_router)
api_router.include_router(membership_auth_router)
api_router.include_router(rbac_router)
api_router.include_router(menu_router)
api_router.include_router(membership_user_router)
api_router.include_router(organization_router)
api_router.include_router(membership_admin_router)
api_router.include_router(group_router)
app.include_router(api_router)
app.add_exception_handler(MembershipError, membership_error_handler)
logger = logging.getLogger(__name__)
audit_retention_scheduler_task: asyncio.Task | None = None


@app.on_event("startup")
async def start_audit_retention_scheduler() -> None:
    global audit_retention_scheduler_task
    ensure_membership_infrastructure()
    audit_retention_scheduler_task = asyncio.create_task(
        run_audit_retention_scheduler(),
        name="audit-log-retention-scheduler",
    )


@app.on_event("shutdown")
async def stop_audit_retention_scheduler() -> None:
    global audit_retention_scheduler_task
    if audit_retention_scheduler_task is None:
        return
    audit_retention_scheduler_task.cancel()
    with suppress(asyncio.CancelledError):
        await audit_retention_scheduler_task
    audit_retention_scheduler_task = None


def env_flag_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().upper() == "TRUE"


DEFAULT_CORS_ALLOW_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://aitc-credit-investigation-chat-bot.vercel.app",
    "https://aitc-credit-investigation-chat-bot-web-ashqnxvdk.vercel.app",
    "https://aitc-creditinvestigationchatbotwebui.onrender.com",
]


def parse_cors_allow_origins() -> List[str]:
    configured = os.getenv("CORS_ALLOW_ORIGINS", "")
    configured_origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return list(dict.fromkeys([*DEFAULT_CORS_ALLOW_ORIGINS, *configured_origins]))


allow_origins = parse_cors_allow_origins()
is_render_deploy = env_flag_enabled("IS_RENDER_DEPLOY", default=False)
allow_origin_regex = (
    r"https://.*\.onrender\.com" if is_render_deploy and not os.getenv("CORS_ALLOW_ORIGINS") else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Disposition",
        "X-Report-History-Id",
        "X-Report-Dashboard-Id",
        "X-Report-Dashboard-Path",
    ],
)


def log_database_diagnostics() -> None:
    diagnostics = build_database_diagnostics()
    logger.warning("Database diagnostics:\n%s", json.dumps(diagnostics, ensure_ascii=False, indent=2))


log_database_diagnostics()


# 建立 VectorStore
# client = chromadb.HttpClient(host="localhost", port=8000)
# embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

# vector_store = Chroma(
#     client=client, collection_name="a-test-collection", embedding_function=embeddings
# )


# Terminal chat mode
async def terminal_chat():
    while True:
        user_input = input("You: ")
        if user_input.lower() in ("exit", "quit"):
            break
        try:
            started_at = perf_counter()
            # graph_answer = graph.invoke({"user_input": user_input})
            graph_answer = graph.invoke(
                {
                    "messages": [HumanMessage(content=user_input)],
                    "user_input": user_input,
                },
                config={"configurable": {"thread_id": "1"}},
            )
            print(f"[timing] terminal_chat.total_graph_to_final_answer took {perf_counter() - started_at:.3f}s")
            # print("graph_answer==========:", graph_answer)

            # print("The answer is :", graph_answer["answer"])
        except Exception as err:
            print("Error:", err, file=sys.stderr)


if __name__ == "__main__":
    host = "0.0.0.0" if is_render_deploy else "localhost"
    default_port = 10000 if is_render_deploy else 3001
    port = int(os.environ.get("PORT", default_port))
    uvicorn.run(app, host=host, port=port)

    # 測試用：建立terminal ai chat bot
    # asyncio.run(terminal_chat())

    # 建立語意化的account title code到vector database
    # asyncio.run(establish_vector_data())
