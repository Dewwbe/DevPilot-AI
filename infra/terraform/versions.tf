terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.60" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # Local state is fine for a solo dev stack. Move to S3 + DynamoDB locking before sharing.
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "devpilot-ai", ManagedBy = "terraform", Environment = var.environment }
  }
}
