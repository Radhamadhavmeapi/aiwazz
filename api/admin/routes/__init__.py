"""All /api/admin routers (each module guards itself with admin.deps)."""
from .content import router as content_router
from .core import router as core_router
from .invites import router as invites_router
from .overview import router as overview_router
from .users import router as users_router
from .users import stop_router

ROUTERS = [core_router, content_router, overview_router, users_router, stop_router, invites_router]
