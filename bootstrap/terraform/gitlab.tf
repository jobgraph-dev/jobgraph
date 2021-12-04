resource "gitlab_project_variable" "jobgraph_bot_gitlab_token" {
  project   = var.GITLAB_PROJECT_ID
  key       = "JOBGRAPH_BOT_GITLAB_TOKEN"
  value     = var.JOBGRAPH_BOT_GITLAB_TOKEN
  protected = true
  masked    = true
}

resource "tls_private_key" "jobgraph_bot_ssh" {
  algorithm = "RSA"
  rsa_bits  = "4096"
}

resource "gitlab_project_variable" "jobgraph_bot_ssh_private_key" {
  project   = var.GITLAB_PROJECT_ID
  key       = "JOBGRAPH_BOT_SSH_PRIVATE_KEY"
  value     = base64encode(tls_private_key.jobgraph_bot_ssh.private_key_pem)
  protected = true
  masked    = true
}

output "jobgraph_ssh_key_public" {
  description = "Please add the following SSH key to your jobgraph bot account"
  value       = tls_private_key.jobgraph_bot_ssh.public_key_openssh
}
