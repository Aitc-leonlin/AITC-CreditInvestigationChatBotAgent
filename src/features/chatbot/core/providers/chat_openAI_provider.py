import os
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI





load_dotenv()


def normalize_openai_base_url(base_url: str) -> str:
    normalized_url = base_url.strip().rstrip("/")
    if normalized_url.endswith("/chat/completions"):
        return normalized_url[: -len("/chat/completions")]
    return normalized_url


def build_chat_model() -> ChatOpenAI:
    llm_provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    if llm_provider == "local":
        local_base_url = normalize_openai_base_url(
            os.getenv("LOCAL_LLM_BASE_URL", "http://192.168.20.169:8004/v1")
        )
        local_model_name = os.getenv(
            "LOCAL_LLM_MODEL_NAME",
            "JunHowie/Qwen3-30B-A3B-Instruct-2507-GPTQ-Int4",
        )
        local_api_key = os.getenv("LOCAL_LLM_API_KEY", "not-needed")
        return ChatOpenAI(
            model=local_model_name,
            api_key=local_api_key,
            base_url=local_base_url,
            use_responses_api=False,
            temperature=0,
        )

    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-5-mini")
    use_responses_api = openai_model_name.startswith("gpt-5")
    return ChatOpenAI(
        model=openai_model_name,
        api_key=openai_api_key,
        use_responses_api=use_responses_api,
        output_version="v0",
    )


chat_model = build_chat_model()

def get_message_text(message: BaseMessage) -> str:
    return message.text().strip()
