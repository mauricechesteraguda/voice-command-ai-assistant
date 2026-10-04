output "database_endpoint" {
  value = aws_db_instance.postgres.address
}
output "database_secret_arn" {
  value = aws_secretsmanager_secret.database.arn
}
output "kms_key_arn" {
  value = aws_kms_key.platform.arn
}
output "backup_vault_name" {
  value = aws_backup_vault.platform.name
}
output "gateway_waf_arn" {
  value = aws_wafv2_web_acl.gateway.arn
}
output "workload_role_arns" {
  value = {
    argo             = try(aws_iam_role.argo[0].arn, null)
    external_secrets = try(aws_iam_role.external_secrets[0].arn, null)
    external_dns     = try(aws_iam_role.external_dns[0].arn, null)
    cert_manager     = try(aws_iam_role.cert_manager[0].arn, null)
  }
}
