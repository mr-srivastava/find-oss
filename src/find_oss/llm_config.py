from crewai import LLM


def build_openai_llm() -> LLM:
    return LLM(
        model="openai/gpt-4o-mini",
        timeout=90,
        max_retries=3,
    )
