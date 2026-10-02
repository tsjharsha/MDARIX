"""Access, administration and platform-control API.

The endpoints live in ``backend/app/access/`` split by domain. This module
only aggregates their routers, in the same order the routes were originally
declared, so request matching is unchanged.
"""

from fastapi import APIRouter

from backend.app.access import (
    catalog,
    configuration,
    governance,
    identity,
    observability,
    platform_customer_admins,
    platform_customers,
    platform_onboarding,
    platform_reference,
    platform_subscriptions,
    platform_tenants,
    session,
    tenant_settings,
)

router = APIRouter()
for _module in (
    observability,
    session,
    identity,
    tenant_settings,
    governance,
    configuration,
    platform_customers,
    platform_onboarding,
    platform_tenants,
    platform_customer_admins,
    platform_subscriptions,
    platform_reference,
    catalog,
):
    router.include_router(_module.router)
