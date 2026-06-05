from __future__ import annotations

from app.models import Operator


ADMIN_ROLES = {"manager", "admin"}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "operator": set(),
    "manager": {
        "access_admin_settings",
        "manage_materials",
        "manage_rates",
        "manage_operators",
        "export_audit_log",
        "create_backup",
        "restore_backup",
        "change_manager_pin",
        "manage_operator_pin_settings",
    },
    "admin": {
        "access_admin_settings",
        "manage_materials",
        "manage_rates",
        "manage_operators",
        "export_audit_log",
        "create_backup",
        "restore_backup",
        "change_manager_pin",
        "manage_operator_pin_settings",
    },
}


def has_permission(operator: Operator | None, permission: str) -> bool:
    if operator is None or not operator.active:
        return False
    return permission in ROLE_PERMISSIONS.get(operator.role, set())


def require_permission(operator: Operator | None, permission: str) -> None:
    if not has_permission(operator, permission):
        raise PermissionError(f"Missing permission: {permission}")


def is_admin_capable(operator: Operator | None) -> bool:
    return operator is not None and operator.active and operator.role in ADMIN_ROLES
