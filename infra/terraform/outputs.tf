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
