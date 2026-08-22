from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse, urlunparse


class ProviderCallError(RuntimeError):
    """Provider failure whose text is safe for logs and persistent diagnostics."""


class ProviderEgressDenied(ProviderCallError):
    """Raised before external content leaves the local machine."""


@dataclass(frozen=True)
class ProviderEndpoint:
    base_url: str
    host: str
    external: bool


class ProviderEgressAuditPort(Protocol):
    def record(
        self,
        *,
        provider_kind: str,
        endpoint_host: str,
        model: str,
        projects: list[str],
        item_count: int,
        outcome: str,
        error_type: str = "",
    ) -> None: ...


@dataclass(frozen=True)
class ProviderEgressPolicy:
    endpoint: ProviderEndpoint
    external_send_allowed: bool = False
    external_projects: tuple[str, ...] = ()

    def authorize(self, projects: list[str]) -> None:
        if not self.endpoint.external:
            return
        normalized_projects = {project.strip() for project in projects if project.strip()}
        allowed_projects = {project.strip() for project in self.external_projects if project.strip()}
        if not normalized_projects:
            raise ProviderEgressDenied("provider_egress_denied: missing_project")
        if not self.external_send_allowed or not normalized_projects.issubset(allowed_projects):
            raise ProviderEgressDenied("provider_egress_denied: project_not_allowed")


def validate_provider_endpoint(base_url: str) -> ProviderEndpoint:
    candidate = base_url.strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("provider URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("provider URL must not contain credentials")
    if parsed.query or parsed.fragment or parsed.params:
        raise ValueError("provider URL must not contain params, query, or fragment")
    is_loopback = _is_loopback_host(parsed.hostname)
    if parsed.scheme == "http" and not is_loopback:
        raise ValueError("non-loopback provider URL must use HTTPS")
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    return ProviderEndpoint(base_url=normalized, host=parsed.hostname, external=not is_loopback)


def safe_provider_error(operation: str, exc: BaseException) -> str:
    del exc
    return f"provider_error:{operation}"


def raise_provider_error(operation: str, exc: BaseException) -> None:
    raise ProviderCallError(safe_provider_error(operation, exc)) from None


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
