import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

# Add project root to sys.path to ensure imports work
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

import os

# Set default environment variables if not present
if "STANDARDS_DIR" not in os.environ:
    standards_dir = project_root / "docs" / "samples"
    os.environ["STANDARDS_DIR"] = str(standards_dir)
    logger.info(f"Set STANDARDS_DIR to default: {standards_dir}")

if "ARTIFACT_ROOT" not in os.environ:
    artifact_root = project_root / "artifacts"
    os.environ["ARTIFACT_ROOT"] = str(artifact_root)
    logger.info(f"Set ARTIFACT_ROOT to default: {artifact_root}")

try:
    from aiwf.domain.models.workflow_state import WorkflowPhase
    from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Ensure you are running this script from the project root or have the environment set up correctly.")
    sys.exit(1)


def main():
    """
    Manual rendering utility for JpaMtProfile prompts.
    
    Example usage:
      python scripts/render_prompts_manual.py \
          --session-id test-session \
          --iteration 1 \
          --bounded-context catalog \
          --entity Product \
          --table app.products \
          --phase both
    """
    parser = argparse.ArgumentParser(description="Render prompts manually using JpaMtProfile.")
    
    parser.add_argument("--session-id", required=True, help="Session identifier")
    parser.add_argument("--iteration", required=True, help="Iteration number")
    parser.add_argument("--bounded-context", required=True, help="Bounded Context name (e.g., catalog)")
    parser.add_argument("--entity", required=True, help="Entity name (e.g., Product)")
    parser.add_argument("--table", required=True, help="Table name (e.g., app.products)")
    parser.add_argument("--scope", default="domain", help="Scope (default: domain)")
    parser.add_argument("--phase", choices=["planning", "generation", "both"], default="both", help="Phase to render (default: both)")
    
    args = parser.parse_args()

    session_id = args.session_id
    iteration = args.iteration
    bounded_context = args.bounded_context
    entity = args.entity
    table = args.table
    scope = args.scope
    phase_selection = args.phase

    # 1. Construct session iteration directory
    session_dir = project_root / ".aiwf" / "sessions" / session_id / f"iteration-{iteration}"
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Session directory: {session_dir}")
    except OSError as e:
        logger.error(f"Failed to create directory {session_dir}: {e}")
        sys.exit(1)

    # 2. Initialize JpaMtProfile
    try:
        # Rely on default config loading logic
        profile = JpaMtProfile()
        logger.info("Initialized JpaMtProfile.")
    except Exception as e:
        logger.error(f"Failed to initialize profile: {e}")
        sys.exit(1)

    # 3. Build context dict
    # Current date in YYYY-MM-DD format
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    context = {
        "TASK_ID": "MANUAL-TEST", # Dummy value as per instructions
        "DEV": "ManualUser",      # Dummy value as per instructions
        "DATE": current_date,
        "ENTITY": entity,
        "SCOPE": scope,
        "TABLE": table,
        "BOUNDED_CONTEXT": bounded_context,
        "SESSION_ID": session_id,
        "PROFILE": "jpa-mt",
        "ITERATION": iteration,
        "scope": scope, # JpaMtProfile expects lowercase 'scope' in context
    }

    # 4. Render and Write Prompts

    # Planning Phase
    if phase_selection in ["planning", "both"]:
        try:
            logger.info(f"Rendering Planning prompt for scope '{scope}'...")
            prompt_content = profile.generate_planning_prompt(context)
            
            output_path = session_dir / "planning-prompt.md"
            output_path.write_text(prompt_content, encoding='utf-8')
            logger.info(f"Wrote Planning prompt to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to render/write Planning prompt: {e}")
            sys.exit(1)

    # Generation Phase
    if phase_selection in ["generation", "both"]:
        try:
            logger.info(f"Rendering Generation prompt for scope '{scope}'...")
            prompt_content = profile.generate_generation_prompt(context)
            
            output_path = session_dir / "generation-prompt.md"
            output_path.write_text(prompt_content, encoding='utf-8')
            logger.info(f"Wrote Generation prompt to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to render/write Generation prompt: {e}")
            sys.exit(1)

    logger.info("Done.")

    logger.info("Done.")

if __name__ == "__main__":
    main()
