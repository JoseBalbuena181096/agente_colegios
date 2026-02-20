import logging
import os
from typing import Optional, Type
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


def get_chat_model(structured_output: Optional[Type[BaseModel]] = None):
    """Returns a configured Chat Model based on LLM_PROVIDER env variable."""
    if LLM_PROVIDER.lower() == "openai":
        return _get_openai_model(structured_output)
    else:
        return _get_google_model(structured_output)


def _get_google_model(structured_output: Optional[Type[BaseModel]] = None):
    """Configuración para Google Gemini."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        logger.warning("GOOGLE_API_KEY not found in environment variables")

    logger.info("Usando modelo Google: %s", GEMINI_MODEL)

    model = ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        temperature=1.0 if "gemini-3" in GEMINI_MODEL else 0,
        google_api_key=google_api_key
    )

    if structured_output:
        model = model.with_structured_output(structured_output)

    return model


def _get_openai_model(structured_output: Optional[Type[BaseModel]] = None):
    """Configuración para OpenAI."""
    from langchain_openai import ChatOpenAI

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        logger.warning("OPENAI_API_KEY not found in environment variables")

    logger.info("Usando modelo OpenAI: %s", OPENAI_MODEL)

    model = ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=0,
        openai_api_key=openai_api_key
    )

    if structured_output:
        model = model.with_structured_output(structured_output, method="function_calling")

    return model
