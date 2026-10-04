# Azure platform backup and recovery

The PostgreSQL Flexible Server uses zone redundancy, geo-redundant backups, and
seven days of point-in-time retention by default. The platform target is **RPO
15 minutes / RTO 60 minutes** for the database and **RPO 24 hours / RTO 4 hours**
for the platform control plane. Teams may raise retention and use a paired region
for stricter service objectives.

Before a restore, freeze Argo promotions and record the incident and selected
restore point. Restore to a new server, validate schema and application health,
then promote the DNS/secret reference through Argo. Never place a password in
Terraform output, logs, or this runbook. Validate the Key Vault and state-storage
soft-delete protections quarterly with a non-production recovery exercise.
