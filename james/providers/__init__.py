"""Model provider adapters used by James.

The provider boundary deliberately stays independent of Hermes.  This lets the
same reply worker run with Codex CLI locally/inside EC2 and use OpenRouter as a
controlled fallback without putting either credential in the repository.
"""

from .router import ProviderRouter
from .types import GenerationResult, ProviderError

__all__ = ["GenerationResult", "ProviderError", "ProviderRouter"]

