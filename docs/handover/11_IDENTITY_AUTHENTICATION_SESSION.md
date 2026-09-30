# Identity, authentication and sessions

Authentication includes sign-in, sign-out, password reset, invitation/activation foundations, tenant membership and role resolution. Session cookies and production authentication fallback behavior are environment-sensitive; production must disable development compatibility paths and enforce secure cookie/reverse-proxy settings.

MFA and high-impact signature ceremonies have foundations and tests, but a complete authenticator/IdP enrollment, recovery and browser evidence set is an explicit validation gate. Never put credentials or API keys in source control or documentation.
