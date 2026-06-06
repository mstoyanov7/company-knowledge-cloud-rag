import re

from rag_api.ports import GenerationResult, PromptContext


class MockLlmAdapter:
    provider_name = "mock"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def generate(self, prompt: PromptContext) -> GenerationResult:
        if not prompt.citations:
            return GenerationResult(
                provider=self.provider_name,
                model=self.model_name,
                answer_text="I could not find that information in the available OneNote notes or readable attachments.",
            )

        highlights = []
        for block, citation in zip(prompt.context_blocks, prompt.citations[:2], strict=False):
            content = _content_from_block(block) or citation.snippet
            highlights.append(_trim_sentences(content, max_sentences=4))

        answer = "### Answer\n\n" + "\n\n".join(f"- {highlight}" for highlight in highlights if highlight)
        return GenerationResult(
            provider=self.provider_name,
            model=self.model_name,
            answer_text=answer,
        )

    async def ready(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.model_name]


def _content_from_block(block: str) -> str:
    marker = "Content:"
    if marker not in block:
        return ""
    return block.split(marker, maxsplit=1)[1].strip()


def _trim_sentences(value: str, *, max_sentences: int) -> str:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", value.strip())
        if sentence.strip()
    ]
    if not sentences:
        return value.strip().rstrip(".") + "."
    selected = sentences[:max_sentences]
    return " ".join(sentence.rstrip(".") + "." for sentence in selected)
