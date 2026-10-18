# One Secrets Manager secret (JSON) read by the Secrets Store CSI driver. Terraform seeds the
# values it knows (database URL, a random webhook secret) and placeholders for the rest. Set the
# real values out-of-band so they never enter Terraform state, e.g.:
#   aws secretsmanager put-secret-value --secret-id devpilot-dev/app --secret-string file://secret.json
resource "random_password" "webhook" {
  length  = 40
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}/app"
  recovery_window_in_days = local.is_prod ? 7 : 0
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    database_url               = "postgresql+psycopg://devpilot:${random_password.db.result}@${aws_db_instance.postgres.address}:5432/devpilot"
    anthropic_api_key          = "REPLACE_ME"
    github_token               = "REPLACE_ME"
    github_webhook_secret      = random_password.webhook.result
    basic_auth_htpasswd        = "REPLACE_ME" # `htpasswd -nbB admin '<password>'`
    github_app_id              = "REPLACE_ME"
    github_app_private_key     = "REPLACE_ME"
    github_app_installation_id = "REPLACE_ME"
  })

  # Once you have put real values, Terraform must not overwrite them.
  lifecycle { ignore_changes = [secret_string] }
}

# IRSA role assumed by the DevPilot ServiceAccount; it can read only this one secret.
data "aws_iam_policy_document" "app_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values   = ["system:serviceaccount:${var.k8s_namespace}:devpilot"]
    }
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "${local.name}-app"
  assume_role_policy = data.aws_iam_policy_document.app_assume.json
}

resource "aws_iam_role_policy" "app_secrets" {
  role = aws_iam_role.app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      Resource = [aws_secretsmanager_secret.app.arn]
    }]
  })
}
