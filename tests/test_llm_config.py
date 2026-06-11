from find_oss.llm_config import build_openai_llm


def test_openai_llm_has_resilient_network_defaults() -> None:
    llm = build_openai_llm()

    assert llm.model == "gpt-4o-mini"
    assert llm.timeout == 90
    assert llm.max_retries == 3
