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

variable "github_oauth_client_id" {
  description = "GitHub OAuth App client id (docs/AUTH.md). Leave empty to keep the app open."
  type        = string
  default     = ""
}

variable "github_oauth_client_secret" {
  type      = string
  sensitive = true
  default   = ""
}

variable "session_secret" {
  description = "Signs session cookies (openssl rand -hex 32)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "allowed_github_users" {
  description = "Comma-separated GitHub logins allowed to sign in; empty = any account"
  type        = string
  default     = ""
}

variable "public_base_url" {
  description = "Public origin, e.g. https://devpilot.example.com. Needed for OAuth behind a load balancer."
  type        = string
  default     = ""
}

variable "desired_count" {
  description = "Set to 0 to stop the app without destroying ECR"
  type        = number
  default     = 1
}

variable "github_repo" {
  description = "owner/name of the GitHub repo allowed to push images to ECR via OIDC"
  type        = string
  default     = "Dewwbe/DevPilot-AI"
}

variable "task_cpu" {
  description = "Fargate CPU units for the whole task (256, 512, 1024...). 512 + 1024 MB is the smallest size that fits all five containers."
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Fargate memory (MB) for the whole task. Must be a valid pairing for task_cpu."
  type        = number
  default     = 1024
}

variable "use_spot" {
  description = "Run on Fargate Spot (about 70% cheaper; may be interrupted and restarted)."
  type        = bool
  default     = true
}
