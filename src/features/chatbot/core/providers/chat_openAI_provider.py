import os
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama





load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")
openai_model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-5-mini")
use_responses_api = openai_model_name.startswith("gpt-5")

chat_model = ChatOpenAI(
    model=openai_model_name,
    api_key=openai_api_key,
    use_responses_api=use_responses_api,
    output_version="v0",
)
# Initialize ChatOllama with a cloud-hosted model
# chat_model = ChatOllama(
#     model="gemma4:31b-cloud",  # Explicitly call the cloud variant
#     temperature=0,
# )

def get_message_text(message: BaseMessage) -> str:
    return message.text().strip()
