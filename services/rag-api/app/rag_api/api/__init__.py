from rag_api.api.routes.answer import router as answer_router
from rag_api.api.routes.openai_compat import router as openai_compat_router
from rag_api.api.routes.system import router as system_router

__all__ = ["answer_router", "openai_compat_router", "system_router"]
