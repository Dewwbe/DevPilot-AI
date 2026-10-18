output "ecr_api_repo" {
  value = aws_ecr_repository.repo["api"].repository_url
}

output "ecr_web_repo" {
  value = aws_ecr_repository.repo["web"].repository_url
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service" {
  value = aws_ecs_service.app.name
}

output "ecr_runner_repo" {
  value = aws_ecr_repository.repo["runner"].repository_url
}

output "github_publish_role_arn" {
  description = "Set as the GitHub repo variable AWS_ROLE_ARN"
  value       = aws_iam_role.github_publish.arn
}
