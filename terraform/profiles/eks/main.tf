provider "aws" {
  region = var.region
}
module "network" {
  source             = "../../modules/network"
  name               = var.name
  region             = var.region
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  tags               = var.tags
}
module "services" {
  source                = "../../modules/platform-services"
  name                  = var.name
  vpc_id                = module.network.vpc_id
  private_subnet_ids    = module.network.private_subnet_ids
  hosted_zone_name      = var.hosted_zone_name
  domain_name           = var.domain_name
  backup_retention_days = 7
  deletion_protection   = var.deletion_protection
  tags                  = var.tags
}
module "cluster" {
  source              = "../../modules/cluster"
  name                = var.name
  kubernetes_version  = var.kubernetes_version
  vpc_id              = module.network.vpc_id
  private_subnet_ids  = module.network.private_subnet_ids
  node_instance_types = var.node_instance_types
  node_min_size       = var.node_min_size
  node_max_size       = var.node_max_size
  node_desired_size   = var.node_desired_size
  kms_key_arn         = module.services.kms_key_arn
  tags                = var.tags
}
// Boundary: Terraform creates the cluster and Argo IAM role; Argo owns workload reconciliation.
