resource "aws_kms_key" "platform" {
  description             = "${var.name} platform encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  tags                    = var.tags
}
resource "aws_kms_alias" "platform" {
  name          = "alias/${var.name}-platform"
  target_key_id = aws_kms_key.platform.key_id
}
resource "aws_secretsmanager_secret" "database" {
  name                    = "${var.name}/postgres"
  kms_key_id              = aws_kms_key.platform.arn
  recovery_window_in_days = 7
  tags                    = var.tags
}
resource "aws_db_subnet_group" "postgres" {
  name       = "${var.name}-postgres"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}
resource "aws_db_instance" "postgres" {
  identifier                    = "${var.name}-postgres"
  engine                        = "postgres"
  engine_version                = "16"
  instance_class                = var.database_instance_class
  allocated_storage             = 20
  storage_encrypted             = true
  kms_key_id                    = aws_kms_key.platform.arn
  db_name                       = var.database_name
  username                      = "platform_admin"
  manage_master_user_password   = true
  master_user_secret_kms_key_id = aws_kms_key.platform.arn
  db_subnet_group_name          = aws_db_subnet_group.postgres.name
  publicly_accessible           = false
  backup_retention_period       = var.backup_retention_days
  backup_window                 = "03:00-03:30"
  maintenance_window            = "sun:04:00-sun:04:30"
  deletion_protection           = var.deletion_protection
  skip_final_snapshot           = false
  final_snapshot_identifier     = "${var.name}-final"
  apply_immediately             = false
  tags = merge(var.tags, {
    "platform:rpo" = "24h"
    "platform:rto" = "4h"
  })
}
data "aws_route53_zone" "this" {
  count        = var.hosted_zone_name == null ? 0 : 1
  name         = var.hosted_zone_name
  private_zone = false
}
resource "aws_route53_record" "database" {
  count   = var.hosted_zone_name == null ? 0 : 1
  zone_id = data.aws_route53_zone.this[0].zone_id
  name    = "postgres.${var.hosted_zone_name}"
  type    = "CNAME"
  ttl     = 60
  records = [aws_db_instance.postgres.address]
}
data "aws_iam_policy_document" "workload_trust" {
  count = var.oidc_issuer == null ? 0 : 1
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_issuer, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_issuer, "https://", "")}:sub"
      values   = var.service_account_subjects
    }
  }
}
resource "aws_iam_role" "argo" {
  count              = var.oidc_issuer == null ? 0 : 1
  name               = "${var.name}-argo"
  assume_role_policy = data.aws_iam_policy_document.workload_trust[0].json
}
resource "aws_iam_role" "external_secrets" {
  count              = var.oidc_issuer == null ? 0 : 1
  name               = "${var.name}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.workload_trust[0].json
}
resource "aws_iam_role" "external_dns" {
  count              = var.oidc_issuer == null ? 0 : 1
  name               = "${var.name}-external-dns"
  assume_role_policy = data.aws_iam_policy_document.workload_trust[0].json
}
resource "aws_iam_role" "cert_manager" {
  count              = var.oidc_issuer == null ? 0 : 1
  name               = "${var.name}-cert-manager"
  assume_role_policy = data.aws_iam_policy_document.workload_trust[0].json
}
resource "aws_iam_role_policy" "external_secrets" {
  count = var.oidc_issuer == null ? 0 : 1
  role  = aws_iam_role.external_secrets[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"]
      Resource = aws_secretsmanager_secret.database.arn
    }]
  })
}
resource "aws_iam_role_policy" "external_dns" {
  count = var.oidc_issuer == null ? 0 : 1
  role  = aws_iam_role.external_dns[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["route53:ChangeResourceRecordSets"]
      Resource = var.hosted_zone_name == null ? "*" : data.aws_route53_zone.this[0].arn
      },
      {
        Effect = "Allow"
        Action = ["route53:ListHostedZones",
        "route53:ListResourceRecordSets"]
        Resource = "*"
    }]
  })
}
resource "aws_backup_vault" "platform" {
  name        = "${var.name}-backup"
  kms_key_arn = aws_kms_key.platform.arn
  tags        = var.tags
}
resource "aws_wafv2_web_acl" "gateway" {
  name  = "${var.name}-gateway"
  scope = "REGIONAL"
  default_action {
    allow {
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name}-gateway"
    sampled_requests_enabled   = false
  }
  rule {
    name     = "managed-common"
    priority = 1
    override_action {
      none {
      }
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-common"
      sampled_requests_enabled   = false
    }
  }
  tags = var.tags
}
