# Authentication and enterprise identity MVP

The local MVP provides password authentication, durable sessions, tenant
membership/roles, password reset, lockout, enrollment and single-use MFA
challenges. Recovery-code primitives are now available: codes are generated
once, stored only as hashes, and consumed exactly once.

The MFA APIs remain the authoritative ceremony for enrollment and governed
signatures. Recovery-code persistence should be attached to the authenticated
user in the deployment migration before enabling account recovery in a hosted
environment.

OIDC/SAML, Okta, Azure AD, enterprise SSO evidence, hosted multi-instance
session validation, and production identity-provider enforcement require
approved external IdPs and deployed infrastructure.
