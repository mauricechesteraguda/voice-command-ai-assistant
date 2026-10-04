output "cluster_name" {
  value = aws_eks_cluster.this.name
}
output "cluster_endpoint" {
  value     = aws_eks_cluster.this.endpoint
  sensitive = true
}
output "cluster_ca_data" {
  value     = aws_eks_cluster.this.certificate_authority[0].data
  sensitive = true
}
output "oidc_provider_arn" {
  value = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${replace(aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")}"
}
output "oidc_issuer_url" {
  value = aws_eks_cluster.this.identity[0].oidc[0].issuer
}
