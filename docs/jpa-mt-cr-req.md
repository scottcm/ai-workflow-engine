# Code Review Request: jpa-mt Template Validation & UserTesting Setup

## Summary

This PR validates the jpa-mt planning prompt template with real Skills Harbor data and establishes a gitignored `UserTesting/` directory for project-specific test data.

## Changes

### 1. Variable Resolution Fix (profiles/jpa_mt/profile.py)
- **Issue:** Profile was stripping engine variables (`{{STANDARDS}}`, `{{PLAN}}`) by replacing unknown vars with empty string
- **Fix:** `_resolve_variables` now returns `match.group(0)` to preserve unknown placeholders
- **Design:** Profile resolves profile vars; engine resolves engine vars; neither tracks the other's list

### 2. UserTesting Directory Structure
- Created `UserTesting/` (gitignored) for project-specific test data
- `UserTesting/skillsharbor/` contains: config.yml, standards/, schema, run-test.py
- Self-contained test environment that simulates full engine flow

### 3. .gitignore Updates
- Changed `profiles/jpa_mt/config.yml` to `profiles/*/config.yml` pattern
- Added `UserTesting/` directory

### 4. Template Validation Script (LIVE/experimental/render_planning_prompt.py)
- Simulates full engine flow: creates session dir, standards bundle, prompt with Output Destination
- Uses `assume_answers=True` for automated workflow testing

## Files Changed

| File | Change |
|------|--------|
| profiles/jpa_mt/profile.py | Variable resolution preserves unknowns |
| tests/unit/profiles/jpa_mt/test_profile.py | Updated test expectations |
| tests/unit/profiles/jpa_mt/test_profile_contracts.py | Updated test expectations |
| .gitignore | Added UserTesting/, updated config pattern |
| UserTesting/README.md | Setup instructions |
| UserTesting/skillsharbor/* | SH-specific test data and scripts |
| LIVE/experimental/render_planning_prompt.py | Template validation script |
| memory.md | Session progress tracking |

## Test Results

- 122 profile unit tests pass
- 14 E2E integration tests pass
- AI execution test: High-quality plan generated for `global.tiers` entity

## Questions for Reviewer

### Architecture

1. **Variable resolution approach:** The profile now preserves unknown `{{VAR}}` placeholders for engine resolution. Is this the right boundary? Alternative: profile could receive engine's variable list and explicitly skip them.

2. **UserTesting location:** Is `UserTesting/` at repo root the right place for project-specific test data? Alternative: `tests/user/` or `.local/`.

### Code Quality

3. **Test script duplication:** `LIVE/experimental/render_planning_prompt.py` and `UserTesting/skillsharbor/run-test.py` have similar code. Should these share a common base, or is duplication acceptable for isolated test scenarios?

4. **Config format:** The `UserTesting/skillsharbor/config.yml` uses a custom format. Should this align with the profile's `config.yml.example` format, or is a separate structure appropriate for test scenarios?

### Standards

5. **Standards files in UserTesting:** We copied `.rules.yml` files into `UserTesting/skillsharbor/standards/`. For production use, should the config point to the real SH repo's standards, or is a copy acceptable for isolated testing?

## Next Steps (After Review)

1. Implement `--project-dir` CLI flag (allows running from any directory)
2. Validate remaining templates (generation, review, revision)
3. Test tenant-scoped entity (e.g., `app.users`)
