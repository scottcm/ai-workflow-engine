# Creating Workflow Profiles

A conceptual and practical guide to implementing custom workflow profiles for the AI Workflow Engine.

---

## Why Profiles Exist

The workflow engine is **domain-agnostic by design**. It knows how to:
- Manage phase transitions (PLAN → GENERATE → REVIEW → REVISE)
- Persist state and files
- Coordinate providers and approvals
- Track iterations

But it knows **nothing** about:
- What makes a good prompt for your domain
- How to parse AI responses for your use case
- What artifacts to extract or where to put them
- What "passing review" means for your domain

**Profiles encapsulate this domain-specific knowledge.** They are the bridge between the generic workflow engine and your specific generation needs.

A profile for generating React components will structure prompts differently than one for generating JPA entities. It will extract `.tsx` files instead of `.java` files. It may define "passing review" as TypeScript compiling without errors. All of this logic lives in the profile, not the engine.

---

## The Core Contract

A profile implements the `WorkflowProfile` abstract base class. The contract is minimal:

### 8 Abstract Methods

| Method | Purpose |
|--------|---------|
| `generate_planning_prompt(context)` | Create the planning phase prompt |
| `process_planning_response(content)` | Parse the plan response |
| `generate_generation_prompt(context)` | Create the code generation prompt |
| `process_generation_response(content, session_dir, iteration)` | Extract code artifacts |
| `generate_review_prompt(context)` | Create the review prompt |
| `process_review_response(content)` | Determine pass/fail |
| `generate_revision_prompt(context)` | Create the revision prompt |
| `process_revision_response(content, session_dir, iteration)` | Extract revised code |

**That's it.** A valid profile can be under 100 lines if your domain is simple.

### Return Types

**Prompts return `PromptResult`:**
```python
PromptResult = str | PromptSections
```
You can return a raw string or structured sections. Most profiles return strings.

**Response processing returns `ProcessingResult`:**
```python
class ProcessingResult(BaseModel):
    status: WorkflowStatus        # IN_PROGRESS, SUCCESS, FAILED, ERROR
    approved: bool = False        # Set True when review passes
    write_plan: WritePlan | None  # Files to write
    messages: list[str]           # Progress messages
    metadata: dict[str, Any]      # Phase-specific data
    error_message: str | None     # Error details
    artifacts: list[Artifact]     # Legacy, rarely used
```

**Files are written via `WritePlan`:**
```python
class WritePlan(BaseModel):
    writes: list[WriteOp]

class WriteOp(BaseModel):
    path: str      # Filename or relative path
    content: str   # File content
```
The engine handles writing files. Profiles just declare what to write.

---

## What Profiles Should Do

These aren't required by the interface, but they're what makes a profile actually useful.

### 1. Declare What Inputs They Need

Your profile needs information to generate prompts. Declare this in `get_metadata()`:

```python
@classmethod
def get_metadata(cls) -> dict[str, Any]:
    return {
        "name": "my-profile",
        "description": "What this profile generates",
        "context_schema": {
            "entity": {"type": "string", "required": True},
            "output_dir": {"type": "string", "required": False, "default": "src"},
        },
    }
```

The `context_schema` tells the CLI what `-c` flags to accept and validates them. This is how users provide `entity=Customer` to your profile.

**Why this matters:** Without declared inputs, users don't know what to provide. The CLI can't validate. Error messages are unhelpful.

### 2. Be Discoverable

Override `get_metadata()` with meaningful information:

```python
@classmethod
def get_metadata(cls) -> dict[str, Any]:
    return {
        "name": "react-ts",
        "description": "React/TypeScript component generation",
        "target_stack": "React 18+ / TypeScript 5+",
        "scopes": ["component", "hook"],  # If you support multiple scopes
        "phases": ["planning", "generation", "review", "revision"],
        "requires_config": False,
        "config_keys": [],
        "context_schema": {...},
    }
```

This enables `aiwf <profile> info` and helps users understand what your profile does.

### 3. Provide Standards (When Needed)

If your domain has coding standards, style guides, or constraints the AI should follow, provide them. Two approaches:

**Inline in prompts (simple):**
```python
def generate_generation_prompt(self, context: dict) -> str:
    return f"""
    Generate code following these standards:
    - Use functional components with hooks
    - Export as named exports
    - Include TypeScript types

    Create: {context['component']}.tsx
    """
```

**Via standards provider (complex):**
```python
def get_default_standards_provider_key(self) -> str:
    return "scoped-layer-fs"  # Built-in file-based provider

def get_standards_config(self) -> dict[str, Any]:
    return {"standards_root": str(Path(__file__).parent / "standards")}
```

Choose based on complexity. If your standards fit in 20 lines, inline them. If you have pages of guidelines, use a standards provider.

### 4. Generate Prompts Appropriate for Your Domain

Your prompts should:
- Provide enough context for quality AI output
- Request output in a format you can parse
- Be consistent across phases

```python
def generate_generation_prompt(self, context: dict) -> str:
    component = context["component"]
    return f"""# Generate React Component: {component}

Create a functional React component with TypeScript.

## Output Format
Wrap each file in markers:
<<<FILE: filename.tsx>>>
code here
<<<END_FILE>>>

## Files to Generate
1. {component}.tsx - Component implementation
2. {component}.test.tsx - Tests
"""
```

**Key insight:** The format you request determines how hard parsing is. Design prompts with parsing in mind.

### 5. Extract and Validate Artifacts

In `process_*_response()`, extract what the AI produced and validate it:

```python
def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
    files = self._extract_files(content)

    if not files:
        return ProcessingResult(
            status=WorkflowStatus.IN_PROGRESS,
            error_message="No code blocks found in response",
        )

    # Validate what we found
    for filename in files:
        if not filename.endswith((".tsx", ".ts")):
            return ProcessingResult(
                status=WorkflowStatus.IN_PROGRESS,
                error_message=f"Unexpected file type: {filename}",
            )

    return ProcessingResult(
        status=WorkflowStatus.IN_PROGRESS,
        write_plan=WritePlan(writes=[
            WriteOp(path=name, content=code)
            for name, code in files.items()
        ]),
        messages=[f"Extracted {len(files)} files"],
    )
```

### 6. Determine Review Outcomes

In `process_review_response()`, decide if generated code passes review:

```python
def process_review_response(self, content: str) -> ProcessingResult:
    # Your domain-specific logic here
    # jpa-mt looks for structured metadata
    # A simpler profile might look for "PASS" or "FAIL"

    passed = "PASS" in content.upper() or "APPROVED" in content.upper()

    return ProcessingResult(
        status=WorkflowStatus.SUCCESS if passed else WorkflowStatus.FAILED,
        metadata={"verdict": "pass" if passed else "fail"},  # Required!
    )
```

**Important:** The engine reads `metadata["verdict"]` to determine workflow flow:
- `"pass"` → workflow completes successfully
- `"fail"` → transitions to REVISE phase

How you determine pass/fail is entirely up to you, but you MUST set the verdict in metadata.

---

## What's Optional

These are implementation choices, not requirements.

### Templates

You can use a template system with `{{include:}}` directives for complex, reusable prompts:

```
templates/
├── base.md
├── planning-prompt.md    # {{include: base.md}}
└── generation-prompt.md
```

**Or** you can use simple f-strings. Templates are a convenience, not a requirement.

### Configuration Classes

You can create a Pydantic model for config validation:

```python
class MyProfileConfig(BaseModel):
    output_format: str = "typescript"
    include_tests: bool = True
```

**Or** you can work directly with the `config` dict. A config class adds type safety but isn't required.

### Multiple Scopes

You can support different generation "scopes":

```python
"scopes": ["component", "hook", "page", "full"]
```

**Or** you can have a single implicit scope. Not every profile needs multiple scopes.

### Complex Standards Providers

You can implement a custom `StandardsProvider` with sophisticated logic.

**Or** you can inline standards in your prompts, use a simple markdown file, or skip standards entirely if your domain doesn't need them.

---

## Pitfalls to Avoid

### 1. File I/O in Profiles

**Wrong:**
```python
def process_generation_response(self, content, session_dir, iteration):
    with open(session_dir / "output.java", "w") as f:
        f.write(content)  # NO - profile should not write files
```

**Right:**
```python
def process_generation_response(self, content, session_dir, iteration):
    return ProcessingResult(
        status=WorkflowStatus.IN_PROGRESS,
        write_plan=WritePlan(writes=[
            WriteOp(path="output.java", content=content)
        ])
    )
```

The engine handles all file I/O. Profiles return what to write, not write it themselves.

### 2. Mutating State

Profiles receive context but should never modify workflow state directly. Return a `ProcessingResult` and let the engine update state.

### 3. Wrong WriteOp Fields

**Wrong:**
```python
WriteOp(type="write", path="file.java", content="...")  # No 'type' field exists
```

**Right:**
```python
WriteOp(path="file.java", content="...")  # Only path and content
```

### 4. Unparseable Output Formats

If you ask the AI to output code without clear markers:

```
Here's the component:
export const Button = () => ...
And here's the test:
describe('Button', () => ...
```

Parsing this reliably is hard. Instead, request explicit markers:

```
<<<FILE: Button.tsx>>>
export const Button = () => ...
<<<END_FILE>>>
```

### 5. Assuming Specific AI Behavior

Don't assume the AI will always format responses exactly as requested. Build robust parsing that handles variations and returns clear errors when extraction fails.

---

## Design Questions to Ask

Before implementing a profile, consider:

### About Your Domain

1. **What am I generating?** Files, configurations, documentation?
2. **What inputs do I need?** Entity name, schema file, target directory?
3. **What standards apply?** Coding style, naming conventions, required patterns?
4. **What defines success?** Compiles? Tests pass? Follows conventions?

### About Prompts

1. **What context does the AI need?** Standards, examples, constraints?
2. **What output format can I reliably parse?** Code fences? Custom markers?
3. **Are my prompts self-contained?** Can the AI produce quality output from what I provide?

### About Parsing

1. **How will I extract files?** Regex? Structured markers?
2. **What validation do I need?** File extensions? Required files?
3. **How do I handle partial success?** Some files extracted but not all?

### About Review

1. **How does the AI indicate pass/fail?** Keyword? Structured format?
2. **What metadata do I need from review?** Issues found? Confidence level?

---

## Suggested Choices

For common decisions, here are sensible defaults:

| Decision | Simple Choice | When to Do More |
|----------|--------------|-----------------|
| Input declaration | Use `context_schema` | Always do this |
| Standards | Inline in prompts | Reusable across profiles, complex guidelines |
| Templates | f-strings | Long prompts, shared components |
| Config validation | Raw dict | Complex validation, IDE support needed |
| Scopes | Single implicit scope | Genuinely different generation modes |
| Code extraction | Regex with markers | Custom parser for complex formats |

---

## Minimal Example

A profile can be simple:

```python
from pathlib import Path
from aiwf.domain.profiles.workflow_profile import WorkflowProfile, PromptResult
from aiwf.domain.models.processing_result import ProcessingResult
from aiwf.domain.models.write_plan import WritePlan, WriteOp
from aiwf.domain.models.workflow_state import WorkflowStatus
import re


class SimpleProfile(WorkflowProfile):
    """Minimal profile that generates a single file."""

    @classmethod
    def get_metadata(cls):
        return {
            "name": "simple",
            "description": "Generate a single file",
            "context_schema": {
                "filename": {"type": "string", "required": True},
            },
        }

    def get_default_standards_provider_key(self) -> str:
        return "scoped-layer-fs"  # Or create your own provider

    def get_standards_config(self):
        return {}  # Provide config if your standards provider needs it

    def generate_planning_prompt(self, context: dict) -> PromptResult:
        return f"Plan how to create {context['filename']}"

    def process_planning_response(self, content: str) -> ProcessingResult:
        return ProcessingResult(status=WorkflowStatus.IN_PROGRESS)

    def generate_generation_prompt(self, context: dict) -> PromptResult:
        return f"""Create {context['filename']}.
Output as: <<<FILE: {context['filename']}>>>content<<<END_FILE>>>"""

    def process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        match = re.search(r"<<<FILE:\s*([^>]+)>>>(.*?)<<<END_FILE>>>", content, re.DOTALL)
        if not match:
            return ProcessingResult(status=WorkflowStatus.IN_PROGRESS, error_message="No file found")
        return ProcessingResult(
            status=WorkflowStatus.IN_PROGRESS,
            write_plan=WritePlan(writes=[WriteOp(path=match.group(1).strip(), content=match.group(2).strip())]),
        )

    def generate_review_prompt(self, context: dict) -> PromptResult:
        return "Review the generated file. Say PASS or FAIL."

    def process_review_response(self, content: str) -> ProcessingResult:
        passed = "PASS" in content.upper()
        return ProcessingResult(
            status=WorkflowStatus.SUCCESS if passed else WorkflowStatus.FAILED,
            metadata={"verdict": "pass" if passed else "fail"},
        )

    def generate_revision_prompt(self, context: dict) -> PromptResult:
        return "Fix the issues and regenerate."

    def process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult:
        return self.process_generation_response(content, session_dir, iteration)
```

This profile works. It declares inputs, generates prompts, extracts code, determines review outcome. No templates, no config classes, no standards files. Add complexity only when you need it.

---

## Registration

For the CLI to discover your profile, create `__init__.py` with a `register` function:

```python
import click
from .profile import MyProfile


def register(cli_group: click.Group):
    """Entry point for profile registration."""

    @cli_group.command("info")
    def info():
        """Show profile information."""
        meta = MyProfile.get_metadata()
        click.echo(f"Profile: {meta['name']}")
        click.echo(f"Description: {meta['description']}")

    return MyProfile
```

---

## Testing

Test profiles in isolation since they're pure functions:

```python
def test_prompt_includes_context():
    profile = MyProfile()
    prompt = profile.generate_generation_prompt({"filename": "test.py"})
    assert "test.py" in prompt


def test_extraction_succeeds():
    profile = MyProfile()
    response = "<<<FILE: test.py>>>print('hi')<<<END_FILE>>>"
    result = profile.process_generation_response(response, Path("/tmp"), 1)
    assert result.write_plan is not None
    assert result.write_plan.writes[0].path == "test.py"


def test_extraction_fails_gracefully():
    profile = MyProfile()
    result = profile.process_generation_response("no code here", Path("/tmp"), 1)
    assert result.error_message is not None
```

---

## Next Steps

- [Creating Providers](creating-providers.md) - Implement AI providers for automated execution
- [Configuration Guide](configuration.md) - Configure profiles and providers
- [EXTENDING.md](../EXTENDING.md) - Complete extension reference
