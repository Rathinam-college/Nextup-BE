from rest_framework import permissions
from .models import User


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        return bool(user.role == User.ROLE_SUPER_ADMIN or user.is_superuser)


class IsGMOrSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        return bool(user.role in [User.ROLE_GENERAL_MANAGER, User.ROLE_SUPER_ADMIN] or user.is_superuser)


class IsDeptManagerOrAbove(permissions.BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.role in [User.ROLE_DEPT_MANAGER, User.ROLE_GENERAL_MANAGER, User.ROLE_SUPER_ADMIN]
            or user.is_superuser
        )


class CanManageDepartment(permissions.BasePermission):
    """
    GM and Super Admin can manage any department.
    Department Managers and Staff can only view their own department.
    """
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(user.role in [User.ROLE_GENERAL_MANAGER, User.ROLE_SUPER_ADMIN] or user.is_superuser)

    def has_object_permission(self, request, view, obj):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if user.role in [User.ROLE_GENERAL_MANAGER, User.ROLE_SUPER_ADMIN] or user.is_superuser:
            return True
        return obj.id == user.department_id


class CanManageStaff(permissions.BasePermission):
    """
    GM and Super Admin can manage staff globally across all departments.
    Department Managers can manage staff only within their own department.
    Staff members cannot create/edit/delete other staff.
    """
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        # Writing requires Dept Manager or GM/SuperAdmin
        return bool(
            user.role in [User.ROLE_DEPT_MANAGER, User.ROLE_GENERAL_MANAGER, User.ROLE_SUPER_ADMIN]
            or user.is_superuser
        )

    def has_object_permission(self, request, view, obj):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if user.role in [User.ROLE_GENERAL_MANAGER, User.ROLE_SUPER_ADMIN] or user.is_superuser:
            return True
        if user.role == User.ROLE_DEPT_MANAGER:
            return obj.department_id == user.department_id and obj.role == User.ROLE_STAFF
        return False
