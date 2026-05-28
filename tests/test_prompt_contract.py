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


def test_prompt_builder_detailed_depth_requests_fuller_structured_answers() -> None:
    prompt = PromptBuilder().build("How do I deploy?", [], [], answer_depth="detailed")

    assert "Answer depth: detailed" in prompt.system_instruction
    assert "all directly relevant details" in prompt.system_instruction
    assert "multiple relevant sentences or paragraphs" in prompt.system_instruction
    assert "summary" in prompt.system_instruction.lower()
    assert prompt.question_analysis is not None
    assert prompt.question_analysis["answer_depth"] == "detailed"


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
