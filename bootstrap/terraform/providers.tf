terraform {
  required_providers {
    gitlab = {
      source = "gitlabhq/gitlab"
    }
  }
}

variable "JOBGRAPH_BOT_GITLAB_TOKEN" {
  type        = string
  description = "GitLab personal access token with `api` scope."
}

variable "GITLAB_PROJECT_ID" {
  type        = string
  description = "Project ID that will get modified."
}

provider "gitlab" {
  token = var.JOBGRAPH_BOT_GITLAB_TOKEN
}
