"""AgentGuard local security-enhancement experiment package.

The package is self-contained: it does not import, copy or reference any local
clone of the upstream AgentGuard repository.
"""
from .config import SERVICE_VERSION

__all__ = ["SERVICE_VERSION"]
__version__ = SERVICE_VERSION
