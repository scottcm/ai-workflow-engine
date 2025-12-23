# Revision Phase Guidelines

## Purpose

The revision phase corrects issues identified during code review. You must:

1. Read and understand all review feedback
2. Fix critical issues (these block approval)
3. Fix minor issues where identified
4. Maintain compliance with all standards

## Code Files to Revise

The following code files were reviewed and require revision:

{{CODE_FILES}}

## Revision Process

1. **Analyze feedback** - Understand what needs to change
2. **Plan corrections** - Determine the minimal changes needed
3. **Apply fixes** - Make the corrections
4. **Verify** - Ensure the fix doesn't break other requirements

## Output Requirements

- Output corrected code using the same format as generation
- Only include files that were modified
- Each file MUST use the `<<<FILE: filename.java>>>` marker
- File content MUST be indented by exactly 4 spaces

## Behavioral Constraints

**You MUST:**
- Address all CRITICAL issues from review
- Change only what is necessary to fix identified issues
- Maintain compliance with standards bundle and approved plan

**You MUST NOT:**
- Refactor or "improve" code beyond the fixes
- Re-generate code after writing it
- Produce multiple drafts in your response

**Output your revision ONCE. Do not revise it.**