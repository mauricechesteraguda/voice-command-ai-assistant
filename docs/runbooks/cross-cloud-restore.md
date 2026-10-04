# Cross-cloud logical restore

Select an encrypted PostgreSQL logical backup, verify checksum, restore into an isolated target profile, run migrations and smoke tests, then promote an immutable digest through a PR. On any failure, retain the original backup and isolated target unchanged, record a structured error, and stop; do not overwrite source data. Cloud availability and pricing remain unverified until provider execution.
