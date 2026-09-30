# Tenant retrieval benchmark

`scripts/benchmark_tenant_retrieval.py` measures evidence indexing and hybrid
query latency against the approved tenant data plane. It applies tenant filters
to both structured and pgvector retrieval and records model/pipeline metadata in
the existing `retrieval_queries` table.

Example:

```powershell
python scripts/benchmark_tenant_retrieval.py `
  --tenant-id <tenant-a-uuid> `
  --query "delayed restart lot 10" `
  --repeats 20
```

The output is synthetic MVP validation evidence. It must not be presented as a
production p99/SLA result until run against the intended production-sized data,
hardware, connection pool, and monitoring configuration.
