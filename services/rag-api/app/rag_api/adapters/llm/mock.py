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
                answer_text="I could not find that information in the available OneNote notes.",
            )

        highlights = []
        for citation in prompt.citations[:2]:
            sentence = citation.snippet.rstrip(".")
            highlights.append(f"{sentence}.")

        sources = "; ".join(dict.fromkeys(citation.title for citation in prompt.citations[:2] if citation.title))
        answer = " ".join(highlights)
        if sources:
            answer = f"{answer}\n\n_Source: {sources}_"
        return GenerationResult(
            provider=self.provider_name,
            model=self.model_name,
            answer_text=answer,
        )

    async def ready(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.model_name]
