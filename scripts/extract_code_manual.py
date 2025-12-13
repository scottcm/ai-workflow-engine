import argparse
import importlib
import os
import sys
from pathlib import Path

# Add project root to sys.path to allow imports from aiwf and profiles.
# Script lives in scripts/, project root is the parent directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aiwf.domain.generation_step import process_generation_response  # noqa: E402


def _eprint(msg: str) -> None:
    """Print an error message to stderr."""
    print(msg, file=sys.stderr)




def _normalize_profile_cli_name(profile: str) -> str:
    """Normalize a CLI profile name.

    Conventions:
    - CLI uses kebab-case (e.g., 'jpa-mt')
    - Filesystem / Python package uses snake_case (e.g., 'jpa_mt')

    For robustness, accept either form on the CLI and normalize to kebab-case.
    """
    return profile.strip().lower().replace('_', '-')


def _load_profile_functions(profile_cli_name: str):
    """Load extractor + writer callables for the given CLI profile name.

    CLI names use kebab-case (e.g., 'jpa-mt'). Profile package paths use snake_case
    (e.g., profiles/jpa_mt -> Python package 'profiles.jpa_mt').
    """
    normalized = _normalize_profile_cli_name(profile_cli_name)
    module_name = normalized.replace('-', '_')
    profile_package = f"profiles.{module_name}"

    profile_dir = PROJECT_ROOT / 'profiles' / module_name
    if not profile_dir.exists():
        raise ImportError(
            f"Unknown profile '{profile_cli_name}'. Expected a profile directory at {profile_dir} (CLI uses kebab-case like 'jpa-mt')."
        )

    try:
        extractor_module = importlib.import_module(f"{profile_package}.bundle_extractor")
        writer_module = importlib.import_module(f"{profile_package}.file_writer")
    except Exception as e:
        raise ImportError(
            f"Failed to import profile '{profile_cli_name}' (package '{profile_package}')."
        ) from e

    extractor = getattr(extractor_module, "extract_files", None) or getattr(extractor_module, "extract", None)
    writer = getattr(writer_module, "write_files", None)
    if extractor is None or not callable(extractor):
        raise AttributeError(
            f"Profile '{profile_cli_name}' extractor not found or not callable (expected 'extract_files')."
        )
    if writer is None or not callable(writer):
        raise AttributeError(
            f"Profile '{profile_cli_name}' writer not found or not callable (expected 'write_files')."
        )

    return extractor, writer


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract code from generation response manually.")
    parser.add_argument("--session-id", required=True, help="Session identifier")
    parser.add_argument("--iteration", type=int, required=True, help="Iteration number (must be >= 1)")
    parser.add_argument("--profile", default="jpa-mt", help="Profile name (kebab-case). Default: jpa-mt")

    args = parser.parse_args()

    if args.iteration < 1:
        _eprint("Error: --iteration must be >= 1")
        sys.exit(1)

    sessions_root = os.environ.get("AIWF_SESSIONS_ROOT", ".aiwf/sessions")
    session_dir = Path(sessions_root) / args.session_id
    iteration_dir = session_dir / f"iteration-{args.iteration}"
    generation_response_path = iteration_dir / "generation-response.md"

    if not generation_response_path.exists():
        _eprint(f"Error: generation-response.md not found at {generation_response_path}")
        sys.exit(1)

    try:
        bundle_content = generation_response_path.read_text(encoding="utf-8")
    except Exception as e:
        _eprint(f"Error: failed to read {generation_response_path}: {e}")
        sys.exit(1)

    try:
        extractor, writer = _load_profile_functions(args.profile)
    except Exception as e:
        _eprint(str(e))
        sys.exit(1)

    try:
        artifacts = process_generation_response(
            bundle_content=bundle_content,
            session_dir=session_dir,
            iteration=args.iteration,
            extractor=extractor,
            writer=writer,
        )
    except Exception as e:
        _eprint(f"Error: failed to process generation response: {e}")
        sys.exit(1)

    print(f"Extracted {len(artifacts)} files:")
    for artifact in artifacts:
        # artifact.file_path is relative to session_dir (e.g., iteration-1/code/File.java)
        print(f"    {artifact.file_path}")

    code_dir = iteration_dir / "code"
    print(f"Written to: {code_dir}")
    sys.exit(0)


if __name__ == "__main__":
    main()
