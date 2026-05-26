from rag_api.adapters.llm.mock import MockLlmAdapter
from rag_api.ports import PromptContext
from rag_api.services.prompt_builder import PromptBuilder

NO_INFORMATION_ANSWER = "I could not find that information in the available OneNote notes."


def test_prompt_builder_enforces_onenote_only_no_information_contract() -> None:
    prompt = PromptBuilder().build("What is the PTO policy?", [], [])

    assert "OneNote-only" in prompt.system_instruction
    assert "Do not use outside knowledge" in prompt.system_instruction
    assert f"reply exactly: {NO_INFORMATION_ANSWER}" in prompt.system_instruction
    assert "Do not include numeric source markers" in prompt.system_instruction


async def _mock_no_context_answer() -> str:
    result = await MockLlmAdapter("mock").generate(
        PromptContext(
            system_instruction="Answer from context.",
            user_question="What is the PTO policy?",
            context_blocks=[],
            citations=[],
        )
    )
    return result.answer_text


def test_mock_llm_returns_no_information_without_citations() -> None:
    import asyncio

    assert asyncio.run(_mock_no_context_answer()) == NO_INFORMATION_ANSWER
