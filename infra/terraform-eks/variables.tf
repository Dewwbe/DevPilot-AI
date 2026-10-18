variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  description = "dev or prod. prod enables Multi-AZ RDS, deletion protection and a NAT per AZ."
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}

variable "admin_cidrs" {
  description = "CIDRs allowed to reach the public Kubernetes API endpoint (your IP as x.x.x.x/32)."
  type        = list(string)
}

variable "cluster_version" {
  type    = string
  default = "1.31"
}

variable "node_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "node_min" {
  type    = number
  default = 2
}

variable "node_max" {
  type    = number
  default = 4
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "k8s_namespace" {
  description = "Namespace the Helm release is installed into (used by the IRSA trust policy)."
  type        = string
  default     = "devpilot"
}
