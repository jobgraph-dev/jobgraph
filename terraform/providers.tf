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

variable "GITLAB_DEFAULT_BRANCH" {
  type        = string
  description = "Default git branch against which schedules will run."
}

variable "SCHEDULES_YML_PATH" {
  type        = string
  description = "Path to jobgraph's schedules.yml file"
}

provider "gitlab" {
  token = var.JOBGRAPH_BOT_GITLAB_TOKEN
}
