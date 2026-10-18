output "cluster_name" {
  value = module.eks.cluster_name
}

output "kubeconfig_command" {
  value = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "redis_url" {
  description = "Helm value config.DEVPILOT_REDIS_URL"
  value       = "redis://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
}

output "app_role_arn" {
  description = "Helm value serviceAccount.roleArn (IRSA role for Secrets Manager access)"
  value       = aws_iam_role.app.arn
}

output "secret_id" {
  description = "Helm value secrets.secretId"
  value       = aws_secretsmanager_secret.app.name
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}

output "ecr_registry" {
  description = "Helm value image.registry"
  value       = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.region}.amazonaws.com"
}

data "aws_caller_identity" "current" {}
