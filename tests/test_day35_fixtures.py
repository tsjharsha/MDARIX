from access_control.fixtures import FIXTURE_TENANTS, FIXTURE_USERS, validate_fixture


def test_day35_fixture_has_four_tenants_and_twenty_five_users():
    validate_fixture()
    assert len(FIXTURE_TENANTS) == 4
    assert len(FIXTURE_USERS) == 25


def test_day35_fixture_users_are_tenant_bound_and_unique():
    tenant_keys = {tenant.key for tenant in FIXTURE_TENANTS}
    assert all(user.tenant_key in tenant_keys for user in FIXTURE_USERS)
    assert len({user.email for user in FIXTURE_USERS}) == 25


def test_day35_fixture_includes_required_tenant_b_customer_administrator():
    customer_admins = [user for user in FIXTURE_USERS if user.role == "CUSTOMER_ADMIN"]
    assert [(user.email, user.tenant_key) for user in customer_admins] == [
        ("r1-user-06@synthetic.invalid", "R1_TENANT_2")
    ]
