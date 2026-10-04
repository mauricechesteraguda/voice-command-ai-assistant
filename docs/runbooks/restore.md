# Source-preserving restore

Restore into a new namespace/database and verify checksum before cutover. Never overwrite the source. If validation fails, delete only the isolated target after preserving logs and backup identifiers, return a structured failure, and require operator approval for retry.
