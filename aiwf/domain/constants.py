from pathlib import Path

# Session storage
DEFAULT_SESSIONS_ROOT = Path(".aiwf/sessions")
SESSION_FILENAME = "session.json"
SESSION_TEMP_SUFFIX = ".json.tmp"

# Session subdirectories (from API contract)
PROMPTS_DIR = "prompts"
RESPONSES_DIR = "responses"
ARTIFACTS_DIR = "artifacts"
PLANS_DIR = "plans"
LOGS_DIR = "logs"

# Standards and templates
STANDARDS_BUNDLE_FILENAME = "standards-bundle.md"