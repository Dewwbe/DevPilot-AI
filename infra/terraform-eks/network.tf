locals {
  name    = "devpilot-${var.environment}"
  is_prod = var.environment == "prod"
}

data "aws_availability_zones" "available" {
  state = "available"
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = local.name
  cidr = "10.20.0.0/16"
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)

  public_subnets      = ["10.20.101.0/24", "10.20.102.0/24"]
  private_subnets     = ["10.20.1.0/24", "10.20.2.0/24"]
  database_subnets    = ["10.20.11.0/24", "10.20.12.0/24"]
  elasticache_subnets = ["10.20.21.0/24", "10.20.22.0/24"]

  create_database_subnet_group    = true
  create_elasticache_subnet_group = true

  # Nodes live in private subnets and reach ECR/Claude/GitHub through NAT.
  enable_nat_gateway     = true
  single_nat_gateway     = !local.is_prod
  one_nat_gateway_per_az = local.is_prod

  enable_dns_hostnames = true

  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}
