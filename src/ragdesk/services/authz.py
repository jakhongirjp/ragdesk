from ragdesk.domain.models import DomainError, Principal, Scope


class ForbiddenError(DomainError):
    pass


def require(principal: Principal, scope: Scope) -> None:
    if not principal.can(scope):
        raise ForbiddenError(f"API key lacks the '{scope}' scope")
