terraform {
    required_providers {
        gitlab = {
            source = "gitlabhq/gitlab"
        }
    }
}

variable "JOBGRAPH_GITLAB_TOKEN" {
    type        = string
    description = "GitLab personal access token with `api` scope."
}

provider "gitlab" {
    token = var.JOBGRAPH_GITLAB_TOKEN
}
