from rag_api.ports import GenerationResult, PromptContext


class MockLlmAdapter:
    provider_name = "mock"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def generate(self, prompt: PromptContext) -> GenerationResult:
        if not prompt.citations:
            answer = (
                "I could not find a relevant onboarding source in the mock index. "
                "Try asking about day-one setup, benefits, or remote work."
            )
            return GenerationResult(
                provider=self.provider_name,
                model=self.model_name,
                answer_text=answer,
            )

        highlights = []
        for citation in prompt.citations[:2]:
            sentence = citation.snippet.rstrip(".")
            highlights.append(f"{sentence}. [{citation.index}]")

        answer = " ".join(highlights)
        return GenerationResult(
            provider=self.provider_name,
            model=self.model_name,
            answer_text=answer,
        )

    async def ready(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.model_name]
