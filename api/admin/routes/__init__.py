"""All /api/admin routers (each module guards itself with admin.deps)."""
from .content import router as content_router
from .core import router as core_router

ROUTERS = [core_router, content_router]
