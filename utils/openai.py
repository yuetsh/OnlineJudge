from openai import AsyncOpenAI, OpenAI

from utils.shortcuts import get_env

BASE_URL = "https://api.deepseek.com"


def get_ai_client() -> OpenAI:
    key = get_env("AI_KEY")
    if not key:
        raise Exception("缺少 AI_KEY")

    return OpenAI(api_key=key, base_url=BASE_URL)


def get_async_ai_client() -> AsyncOpenAI:
    key = get_env("AI_KEY")
    if not key:
        raise Exception("缺少 AI_KEY")

    return AsyncOpenAI(api_key=key, base_url=BASE_URL)
