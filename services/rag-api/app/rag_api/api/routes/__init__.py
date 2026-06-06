from rag_api.api.routes.admin import router as admin_router
from rag_api.api.routes.answer import router as answer_router
from rag_api.api.routes.auth import router as auth_router
from rag_api.api.routes.documents import router as documents_router
from rag_api.api.routes.feedback import router as feedback_router
from rag_api.api.routes.openai_compat import router as openai_compat_router
from rag_api.api.routes.system import router as system_router
from rag_api.api.routes.topics import router as topics_router

__all__ = [
    "admin_router",
    "answer_router",
    "auth_router",
    "documents_router",
    "feedback_router",
    "openai_compat_router",
    "system_router",
    "topics_router",
]
