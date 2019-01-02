{{gcloud}} alpha genomics pipelines run \
  --pipeline-file {{pipeline_yaml}} \
  --zones {{google_zone}} \
  --logging gs://{{workflow_bucket}}/logging \
  --inputs-from-file WDL={{wdl_path}} \
  --inputs-from-file WORKFLOW_INPUTS={{inputs_json}} \
  --inputs-from-file WORKFLOW_OPTIONS={{options_json}} \
  --inputs WORKSPACE=gs://{{workflow_bucket}}/workspace \
  --inputs OUTPUTS=gs://{{workflow_bucket}}/{{output_folder}}
