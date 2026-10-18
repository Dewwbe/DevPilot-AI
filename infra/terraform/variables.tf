variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "allowed_cidr" {
  description = "Your public IP as a CIDR, e.g. 203.0.113.7/32. The dashboard has no login, so do not use 0.0.0.0/0."
  type        = string
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "claude_model" {
  type    = string
  default = "claude-sonnet-5-5"
}

variable "anthropic_api_key" {
  description = "Stored in the task definition and Terraform state (local, gitignored). Fine for dev only."
  type        = string
  sensitive   = true
  default     = ""
}

variable "github_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "desired_count" {
  description = "Set to 0 to stop the app without destroying ECR"
  type        = number
  default     = 1
}
