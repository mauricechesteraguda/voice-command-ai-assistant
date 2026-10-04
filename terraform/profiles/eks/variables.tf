variable "name" {
  type    = string
  default = "voice-platform"
}
variable "region" {
  type    = string
  default = "us-east-1"
}
variable "availability_zones" {
  type    = list(string)
  default = []
}
variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}
variable "domain_name" {
  type    = string
  default = null
}
variable "hosted_zone_name" {
  type    = string
  default = null
}
variable "kubernetes_version" {
  type    = string
  default = "1.31"
}
variable "node_instance_types" {
  type    = list(string)
  default = ["t3.medium"]
}
variable "node_min_size" {
  type    = number
  default = 2
}
variable "node_max_size" {
  type    = number
  default = 6
}
variable "node_desired_size" {
  type    = number
  default = 2
}
variable "deletion_protection" {
  type    = bool
  default = true
}
variable "oidc_issuer" {
  type    = string
  default = null
}
variable "oidc_provider_arn" {
  type    = string
  default = null
}
variable "tags" {
  type = map(string)
  default = {
    ManagedBy = "terraform"
    Platform  = "voice-command-ai-assistant"
  }
}
