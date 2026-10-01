"""Evidence chunk embeddings can hold vectors of more than one model (local language model: 384 dimensions).

The column loses its fixed 32 dimensions; existing hash-model rows are kept unchanged. Each model gets its own partial
HNSW index on a typed cast, which is what similarity search uses (it always filters by model and casts to its size).
Downgrade removes rows of other sizes and restores the original 32-dimension column and index.
"""

from alembic import op

revision = "md06multimodelembeddings"
down_revision = "md05rlssystemscope"
branch_labels = None
depends_on = None

INDEXES = {
    # index name: (embedding_model, dimension)
    "ix_chunk_embeddings_hash32_hnsw": ("mdarix-hash-bow-32", 32),
    "ix_chunk_embeddings_bge384_hnsw": ("BAAI/bge-small-en-v1.5", 384),
}


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embeddings_embedding_hnsw")
    op.execute("ALTER TABLE evidence_chunk_embeddings ALTER COLUMN embedding TYPE vector USING embedding::vector")
    for name, (model, dimension) in INDEXES.items():
        op.execute(
            f"CREATE INDEX {name} ON evidence_chunk_embeddings "
            f"USING hnsw ((embedding::vector({dimension})) vector_cosine_ops) "
            f"WHERE indexing_status = 'INDEXED' AND embedding_model = '{model}'"
        )


def downgrade() -> None:
    for name in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    op.execute("DELETE FROM evidence_chunk_embeddings WHERE embedding IS NOT NULL AND vector_dims(embedding) <> 32")
    op.execute(
        "ALTER TABLE evidence_chunk_embeddings ALTER COLUMN embedding TYPE vector(32) USING embedding::vector(32)"
    )
    op.execute(
        "CREATE INDEX ix_chunk_embeddings_embedding_hnsw "
        "ON evidence_chunk_embeddings USING hnsw (embedding vector_cosine_ops) "
        "WHERE indexing_status = 'INDEXED'"
    )
