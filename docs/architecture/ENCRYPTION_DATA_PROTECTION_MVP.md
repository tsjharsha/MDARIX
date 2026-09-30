# Encryption and data protection MVP

The MVP now has a provider-neutral encryption policy contract and tenant-bound
envelope metadata. Key references are scoped to the tenant and carry an
explicit version and AES-256-GCM algorithm declaration. Secret material remains
outside the application and must be resolved by the configured KMS/Vault
adapter.

The policy validator checks declarations for application TLS, database TLS,
database-at-rest encryption, backup encryption, object-storage encryption, and
key rotation. It is a configuration guard, not proof that infrastructure is
encrypted.

Production TLS 1.3, PostgreSQL TLS, managed database encryption, KMS/Key Vault,
encrypted backups, rotation evidence, and object-storage lifecycle validation
remain deployment gates requiring certificates, keys, and hosted targets.
