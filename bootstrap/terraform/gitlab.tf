resource "gitlab_project_variable" "jobgraph_bot_gitlab_token" {
  project   = var.GITLAB_PROJECT_ID
  key       = "JOBGRAPH_BOT_GITLAB_TOKEN"
  value     = var.JOBGRAPH_BOT_GITLAB_TOKEN
  protected = true
  masked    = true
}
