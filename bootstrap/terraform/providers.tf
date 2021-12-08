terraform {
  required_providers {
    gitlab = {
      source = "gitlabhq/gitlab"
    }
  }
}

variable "JOBGRAPH_BOT_GITLAB_TOKEN" {
  type        = string
  description = "GitLab personal access token used by jobgraph to update Gitlab CI schedules. Must have the `api` scope. User must have the `committer` role."
}

variable "MAINTAINER_GITLAB_TOKEN" {
  type        = string
  description = "GitLab personal access used to set up jobgraph. Must have the `api` scope. User must have the `maintainer` role."
}

variable "GITLAB_PROJECT_ID" {
  type        = string
  description = "Project ID that will get modified."
}

provider "gitlab" {
  token = var.MAINTAINER_GITLAB_TOKEN
}

provider "tls" {}
