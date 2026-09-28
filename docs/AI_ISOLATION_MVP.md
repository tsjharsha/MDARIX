# AI isolation MVP contract

All prompt-cache keys must be generated with `tenant_cache_key(tenant_id, ...)`.
All vector indexes must use `tenant_vector_namespace(tenant_id, index_name)`.
The assertion helpers are intended to run at the adapter boundary before a
Redis or vector-store read/write. A cache hit from another tenant is therefore
rejected rather than returned.

The local MVP proves deterministic key/namespace separation and poisoning
rejection. Redis deployment, hosted vector-store namespace enforcement, and
multi-instance persistence remain deployment validations; no production claim
is made by the local tests.
