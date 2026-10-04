variable "project_id" { type = string }
variable "billing_account_id" {
  type    = string
  default = ""
}
variable "monthly_budget_usd" {
  type    = number
  default = 250
}
variable "region" {
  type    = string
  default = "us-central1"
}
variable "zone" {
  type    = string
  default = "us-central1-a"
}
variable "name" {
  type    = string
  default = "voice-platform"
}
variable "environment" {
  type    = string
  default = "dev"
}
variable "network_cidr" {
  type    = string
  default = "10.40.0.0/16"
}
variable "pods_cidr" {
  type    = string
  default = "10.41.0.0/16"
}
variable "services_cidr" {
  type    = string
  default = "10.42.0.0/20"
}
variable "master_cidr" {
  type    = string
  default = "172.16.0.0/28"
}
variable "node_machine_type" {
  type    = string
  default = "e2-standard-2"
}
variable "node_min_count" {
  type    = number
  default = 1
}
variable "node_max_count" {
  type    = number
  default = 3
}
variable "gke_release_channel" {
  type    = string
  default = "REGULAR"
}
variable "dns_name" {
  type    = string
  default = "platform.example."
}
variable "enable_dns_record" {
  type    = bool
  default = false
}
variable "gateway_ip" {
  type    = string
  default = ""
}
variable "log_bucket_name" {
  type    = string
  default = ""
}
variable "sql_tier" {
  type    = string
  default = "db-custom-2-7680"
}
variable "sql_backup_start_time" {
  type    = string
  default = "03:00"
}
variable "rpo_hours" {
  type    = number
  default = 24
}
variable "rto_hours" {
  type    = number
  default = 4
}

variable "argo_namespace" {
  type    = string
  default = "argocd"
}
variable "eso_namespace" {
  type    = string
  default = "external-secrets"
}
variable "externaldns_namespace" {
  type    = string
  default = "external-dns"
}
variable "cert_manager_namespace" {
  type    = string
  default = "cert-manager"
}

variable "labels" {
  type    = map(string)
  default = { managed-by = "terraform", platform = "voice-command" }
}
