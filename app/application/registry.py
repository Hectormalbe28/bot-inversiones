from app.domain.models import ProviderStatus


class ProviderRegistry:
    def __init__(self, providers: tuple[ProviderStatus, ...]):
        self._providers = {provider.provider: provider for provider in providers}
        if len(self._providers) != len(providers):
            raise ValueError("Duplicate provider registration")

    def list(self) -> tuple[ProviderStatus, ...]:
        return tuple(self._providers[name] for name in sorted(self._providers))
