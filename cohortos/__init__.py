"""
CohortOS — installable domain package (Portions 0–7).

Public surface for integrators (Electron, FastAPI, scripts):

    from cohortos import CohortOSApp, create_app
    app = create_app(mode="offline-first")
    summary = app.bootstrap_centre(name="My Centre")
"""

from services.app import CohortOSApp, create_app
from models.base import TenantContext, DataAccessLayer

__version__ = "0.10.0"
__all__ = [
    "CohortOSApp",
    "create_app",
    "TenantContext",
    "DataAccessLayer",
    "__version__",
]
