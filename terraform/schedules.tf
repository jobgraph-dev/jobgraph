locals {
  schedules_config = yamldecode(file(var.SCHEDULES_YML_PATH))
}

resource "gitlab_pipeline_schedule" "schedules" {
  for_each = local.schedules_config.jobs

  active      = true
  cron        = each.value.cron
  description = "[jobgraph] ${each.value.description}"
  project     = "30264497"
  ref         = "main"
}

resource "gitlab_pipeline_schedule_variable" "schedules" {
  for_each = local.schedules_config.jobs

  key                  = "TARGET_JOBS_METHOD"
  pipeline_schedule_id = gitlab_pipeline_schedule.schedules[each.key].id
  project              = gitlab_pipeline_schedule.schedules[each.key].project
  value                = each.value.target_jobs_method
}
