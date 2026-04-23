from shared_schemas import AppSettings

from rag_api.ports import LlmPort, RetrievalPort


class SystemService:
    def __init__(self, *, llm: LlmPort, retriever: RetrievalPort, settings: AppSettings) -> None:
        self.llm = llm
        self.retriever = retriever
        self.settings = settings

    async def health(self) -> dict[str, str]:
        return {"status": "ok"}

    async def ready(self) -> dict[str, object]:
        return {
            "status": "ready" if await self.llm.ready() and await self.retriever.ready() else "degraded",
            "checks": {
                "llm": await self.llm.ready(),
                "retriever": await self.retriever.ready(),
            },
        }

    async def version(self) -> dict[str, str]:
        return {
            "name": self.settings.app_name,
            "version": self.settings.app_version,
            "environment": self.settings.app_env,
        }
