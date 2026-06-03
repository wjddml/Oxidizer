# config.yaml
project:
  name: "Oxidizer"

paths:
  prompts_dir: "prompts"
  data_dir: "data"

llm:
  provider: "claude"         # gemini | claude | gpt
  model: "claude-sonnet-4-20250514"
  temperature: 0.2

agent:
  max_retries: 5
  timeout_seconds: 60
  memory_limit_mb: 1024
