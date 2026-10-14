from fastapi import FastAPI

from yweb.rbac.api import create_permission_router


class FakePermission:
    pass


class FakeRole:
    pass


class FakeSubjectRole:
    pass


class FakeRolePermission:
    pass


class FakeSubjectPermission:
    pass


class FakeAPIResource:
    pass


def _route_paths(api_resource_model=None) -> set[str]:
    app = FastAPI()
    router = create_permission_router(
        permission_model=FakePermission,
        role_model=FakeRole,
        subject_role_model=FakeSubjectRole,
        role_permission_model=FakeRolePermission,
        subject_permission_model=FakeSubjectPermission,
        api_resource_model=api_resource_model,
        prefix="/rbac",
    )
    app.include_router(router)
    return {route.path for route in app.routes}


def test_api_resource_routes_are_absent_without_model():
    paths = _route_paths(api_resource_model=None)

    assert "/rbac/permissions/list" in paths
    assert "/rbac/api-resources/list" not in paths
    assert "/rbac/api-resources/batch-set-permission" not in paths


def test_api_resource_routes_are_included_with_model():
    paths = _route_paths(api_resource_model=FakeAPIResource)

    assert "/rbac/api-resources/list" in paths
    assert "/rbac/api-resources/get" in paths
    assert "/rbac/api-resources/create" in paths
    assert "/rbac/api-resources/modules/list" in paths
    assert "/rbac/api-resources/batch-set-permission" in paths
