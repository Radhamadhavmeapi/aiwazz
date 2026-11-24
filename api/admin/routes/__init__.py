"""All /api/admin routers (each module guards itself with admin.deps)."""
from .billing import router as billing_router
from .comms import router as comms_router
from .content import router as content_router
from .core import router as core_router
from .governance import router as governance_router
from .invites import router as invites_router
from .overview import router as overview_router
from .plans import router as plans_router
from .product import router as product_router
from .support import router as support_router
from .system import router as system_router
from .users import router as users_router
from .users import stop_router

ROUTERS = [core_router, content_router, overview_router, users_router, stop_router, invites_router, billing_router,
           plans_router, support_router, product_router, system_router, comms_router, governance_router]
