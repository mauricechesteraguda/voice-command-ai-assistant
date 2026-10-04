variable "name" {
  type = string
}
variable "vpc_id" {
  type = string
}
variable "private_subnet_ids" {
  type = list(string)
}
variable "database_name" {
  type    = string
  default = "platform"
}
variable "database_instance_class" {
  type    = string
  default = "db.t4g.micro"
}
variable "hosted_zone_name" {
  type    = string
  default = null
}
variable "domain_name" {
  type    = string
  default = null
}
variable "oidc_issuer" {
  type    = string
  default = null
}
variable "oidc_provider_arn" {
  type    = string
  default = null
}
variable "service_account_subjects" {
  type    = list(string)
  default = ["system:serviceaccount:argocd:argocd-controller", "system:serviceaccount:external-secrets:external-secrets", "system:serviceaccount:external-dns:external-dns", "system:serviceaccount:cert-manager:cert-manager"]
}
variable "backup_retention_days" {
  type    = number
  default = 7
}
variable "deletion_protection" {
  type    = bool
  default = true
}
variable "tags" {
  type = map(string)
  default = {
  }
}
