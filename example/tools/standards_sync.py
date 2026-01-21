#!/usr/bin/env python3
"""
Standards Document Sync Script

Parses markdown standards documents with embedded markers and generates
terse YAML for AI/token-efficient code reviews.

Commands:
  generate  - Generate YAML from MD source
  validate  - Validate MD structure without generating
  check     - Check if YAML matches current MD
  extract   - Extract rules for AI review (filtered)
  stats     - Show statistics about the document

Usage:
  python standards_sync.py generate standards.md
  python standards_sync.py validate standards.md
  python standards_sync.py check standards.md
  python standards_sync.py extract standards.md --section python.security
  python standards_sync.py stats standards.md
"""

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


# Patterns for parsing markers
SECTION_START = re.compile(r"<!--\s*@section\s+(\S+)(?:\s+(.+?))?\s*-->")
SECTION_END = re.compile(r"<!--\s*@/section\s*-->")
RULE_START = re.compile(r"<!--\s*@rule\s+(\S+)\s+([CMm])\s*-->")
RULE_END = re.compile(r"<!--\s*@/rule\s*-->")

# Rule ID validation
RULE_ID_PATTERN = re.compile(r"^[A-Z]{2,4}-[A-Z]{2,5}-\d{3}$")

VALID_SEVERITIES = {"C", "M", "m"}


@dataclass
class Rule:
    """A single rule extracted from markdown."""
    id: str
    severity: str
    summary: str
    full_text: str
    line_number: int


@dataclass
class Section:
    """A section containing rules and/or subsections."""
    key: str
    description: str | None
    rules: list[Rule] = field(default_factory=list)
    subsections: dict[str, "Section"] = field(default_factory=dict)
    line_number: int = 0


@dataclass
class ParseResult:
    """Result of parsing a standards document."""
    sections: dict[str, Section]
    errors: list[str]
    warnings: list[str]
    source_hash: str


def parse_document(content: str) -> ParseResult:
    """
    Parse markdown content with markers into structured data.
    
    Returns ParseResult with sections, errors, and warnings.
    """
    lines = content.split("\n")
    errors: list[str] = []
    warnings: list[str] = []
    
    # Stack for tracking nested sections
    section_stack: list[Section] = []
    root_sections: dict[str, Section] = {}
    
    # Current rule being parsed
    current_rule: Rule | None = None
    rule_content_lines: list[str] = []
    
    # Track all rule IDs for duplicate detection
    all_rule_ids: dict[str, int] = {}  # id -> line number
    
    i = 0
    while i < len(lines):
        line = lines[i]
        line_num = i + 1  # 1-indexed for error messages
        
        # Check for section start
        section_match = SECTION_START.search(line)
        if section_match:
            if current_rule:
                errors.append(f"Line {line_num}: Section start inside unclosed rule {current_rule.id}")
            
            key = section_match.group(1)
            desc = section_match.group(2)
            
            new_section = Section(key=key, description=desc, line_number=line_num)
            
            if section_stack:
                # Nested section
                parent = section_stack[-1]
                if key in parent.subsections:
                    errors.append(f"Line {line_num}: Duplicate section key '{key}' in {parent.key}")
                parent.subsections[key] = new_section
            else:
                # Root section
                if key in root_sections:
                    errors.append(f"Line {line_num}: Duplicate root section key '{key}'")
                root_sections[key] = new_section
            
            section_stack.append(new_section)
            i += 1
            continue
        
        # Check for section end
        if SECTION_END.search(line):
            if current_rule:
                errors.append(f"Line {line_num}: Section end inside unclosed rule {current_rule.id}")
            
            if not section_stack:
                errors.append(f"Line {line_num}: Unexpected @/section without matching @section")
            else:
                section_stack.pop()
            i += 1
            continue
        
        # Check for rule start
        rule_match = RULE_START.search(line)
        if rule_match:
            if current_rule:
                errors.append(f"Line {line_num}: Rule start inside unclosed rule {current_rule.id}")
            
            rule_id = rule_match.group(1)
            severity = rule_match.group(2)
            
            # Validate rule ID format
            if not RULE_ID_PATTERN.match(rule_id):
                errors.append(f"Line {line_num}: Invalid rule ID format '{rule_id}' (expected XX-XXX-000)")
            
            # Check for duplicates
            if rule_id in all_rule_ids:
                errors.append(f"Line {line_num}: Duplicate rule ID '{rule_id}' (first seen at line {all_rule_ids[rule_id]})")
            else:
                all_rule_ids[rule_id] = line_num
            
            # Validate severity
            if severity not in VALID_SEVERITIES:
                errors.append(f"Line {line_num}: Invalid severity '{severity}' (expected C, M, or m)")
            
            current_rule = Rule(
                id=rule_id,
                severity=severity,
                summary="",
                full_text="",
                line_number=line_num,
            )
            rule_content_lines = []
            i += 1
            continue
        
        # Check for rule end
        if RULE_END.search(line):
            if not current_rule:
                errors.append(f"Line {line_num}: Unexpected @/rule without matching @rule")
            else:
                # Extract summary (first non-empty line)
                summary = ""
                full_lines = []
                for content_line in rule_content_lines:
                    stripped = content_line.strip()
                    if not summary and stripped:
                        summary = stripped
                    full_lines.append(content_line)
                
                if not summary:
                    errors.append(f"Line {line_num}: Rule {current_rule.id} has no summary line")
                
                current_rule.summary = summary
                current_rule.full_text = "\n".join(full_lines).strip()
                
                # Add rule to current section
                if section_stack:
                    section_stack[-1].rules.append(current_rule)
                else:
                    warnings.append(f"Line {current_rule.line_number}: Rule {current_rule.id} is not inside any section")
                
                current_rule = None
                rule_content_lines = []
            i += 1
            continue
        
        # Accumulate rule content
        if current_rule:
            rule_content_lines.append(line)
        
        i += 1
    
    # Check for unclosed elements
    if current_rule:
        errors.append(f"Line {current_rule.line_number}: Unclosed rule {current_rule.id}")
    
    if section_stack:
        for section in section_stack:
            errors.append(f"Line {section.line_number}: Unclosed section '{section.key}'")
    
    # Compute source hash for change detection
    source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    
    return ParseResult(
        sections=root_sections,
        errors=errors,
        warnings=warnings,
        source_hash=source_hash,
    )


def section_to_dict(section: Section) -> dict[str, Any]:
    """Convert a Section to nested dict for YAML output."""
    result: dict[str, Any] = {}
    
    # Add rules at this level
    for rule in section.rules:
        result[rule.id] = f"{rule.severity}: {rule.summary}"
    
    # Add subsections
    for key, subsection in section.subsections.items():
        result[key] = section_to_dict(subsection)
    
    return result


def generate_yaml(parse_result: ParseResult, source_path: Path) -> str:
    """Generate YAML string from parsed result."""
    # Build nested dict
    data: dict[str, Any] = {}
    for key, section in parse_result.sections.items():
        data[key] = section_to_dict(section)
    
    # Generate header comment
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = f"""# Auto-generated from {source_path.name}
# DO NOT EDIT - changes will be overwritten
# Generated: {timestamp}
# Source hash: {parse_result.source_hash}

"""
    
    # Generate YAML
    yaml_content = yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
        width=120,
    )
    
    return header + yaml_content


def get_yaml_path(md_path: Path) -> Path:
    """Get the corresponding YAML path for a markdown file."""
    return md_path.with_suffix(".rules.yml")


def extract_source_hash(yaml_content: str) -> str | None:
    """Extract source hash from YAML header comment."""
    match = re.search(r"# Source hash: ([a-f0-9]+)", yaml_content)
    return match.group(1) if match else None


def flatten_rules(
    sections: dict[str, Section],
    prefix: str = "",
) -> dict[str, dict[str, str]]:
    """Flatten sections into {path: {rule_id: rule_text}} for extraction."""
    result: dict[str, dict[str, str]] = {}
    
    for key, section in sections.items():
        path = f"{prefix}.{key}" if prefix else key
        
        if section.rules:
            result[path] = {
                rule.id: f"{rule.severity}: {rule.summary}"
                for rule in section.rules
            }
        
        # Recurse into subsections
        sub_result = flatten_rules(section.subsections, path)
        result.update(sub_result)
    
    return result


def get_stats(parse_result: ParseResult) -> dict[str, Any]:
    """Calculate statistics for parsed document."""
    flat = flatten_rules(parse_result.sections)
    
    stats = {
        "total_rules": 0,
        "by_severity": {"C": 0, "M": 0, "m": 0},
        "by_section": {},
        "section_count": 0,
    }
    
    for path, rules in flat.items():
        stats["section_count"] += 1
        stats["by_section"][path] = len(rules)
        stats["total_rules"] += len(rules)
        
        for rule_text in rules.values():
            if rule_text.startswith("C:"):
                stats["by_severity"]["C"] += 1
            elif rule_text.startswith("M:"):
                stats["by_severity"]["M"] += 1
            elif rule_text.startswith("m:"):
                stats["by_severity"]["m"] += 1
    
    return stats


# --- Commands ---

def cmd_generate(args: argparse.Namespace) -> int:
    """Generate YAML from MD source."""
    md_path = Path(args.file)
    
    if not md_path.exists():
        print(f"Error: File not found: {md_path}", file=sys.stderr)
        return 1
    
    content = md_path.read_text(encoding="utf-8")
    result = parse_document(content)
    
    # Report errors and warnings
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    
    if result.errors:
        print(f"\nFound {len(result.errors)} error(s):", file=sys.stderr)
        for error in result.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    
    # Generate YAML
    yaml_content = generate_yaml(result, md_path)
    yaml_path = get_yaml_path(md_path) if not args.output else Path(args.output)
    
    yaml_path.write_text(yaml_content, encoding="utf-8")
    
    stats = get_stats(result)
    print(f"Generated {yaml_path}")
    print(f"  {stats['total_rules']} rules in {stats['section_count']} sections")
    
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate MD structure without generating."""
    md_path = Path(args.file)
    
    if not md_path.exists():
        print(f"Error: File not found: {md_path}", file=sys.stderr)
        return 1
    
    content = md_path.read_text(encoding="utf-8")
    result = parse_document(content)
    
    # Report warnings
    for warning in result.warnings:
        print(f"Warning: {warning}")
    
    # Report errors
    if result.errors:
        print(f"\nFound {len(result.errors)} error(s):")
        for error in result.errors:
            print(f"  - {error}")
        return 1
    
    stats = get_stats(result)
    print(f"✓ Valid: {stats['total_rules']} rules in {stats['section_count']} sections")
    
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Check if YAML matches current MD."""
    md_path = Path(args.file)
    yaml_path = get_yaml_path(md_path)
    
    if not md_path.exists():
        print(f"Error: File not found: {md_path}", file=sys.stderr)
        return 1
    
    if not yaml_path.exists():
        print(f"YAML file does not exist: {yaml_path}")
        print("Run 'generate' to create it.")
        return 1
    
    # Parse MD and get hash
    content = md_path.read_text(encoding="utf-8")
    result = parse_document(content)
    
    if result.errors:
        print(f"Error: MD has validation errors. Run 'validate' first.", file=sys.stderr)
        return 1
    
    # Get hash from existing YAML
    yaml_content = yaml_path.read_text(encoding="utf-8")
    existing_hash = extract_source_hash(yaml_content)
    
    if existing_hash == result.source_hash:
        print(f"✓ YAML is up-to-date with MD (hash: {result.source_hash})")
        return 0
    else:
        print(f"✗ YAML is out of date")
        print(f"  MD hash:   {result.source_hash}")
        print(f"  YAML hash: {existing_hash}")
        print("Run 'generate' to update.")
        return 1


def cmd_extract(args: argparse.Namespace) -> int:
    """Extract rules for AI review."""
    md_path = Path(args.file)
    
    if not md_path.exists():
        print(f"Error: File not found: {md_path}", file=sys.stderr)
        return 1
    
    content = md_path.read_text(encoding="utf-8")
    result = parse_document(content)
    
    if result.errors:
        print(f"Error: MD has validation errors. Run 'validate' first.", file=sys.stderr)
        return 1
    
    flat = flatten_rules(result.sections)
    
    # Filter by section if specified
    if args.section:
        filtered = {}
        for path, rules in flat.items():
            if path.startswith(args.section) or args.section in path:
                filtered[path] = rules
        flat = filtered
    
    # Filter by severity if specified
    if args.severity:
        for path in list(flat.keys()):
            flat[path] = {
                rid: text for rid, text in flat[path].items()
                if text.startswith(f"{args.severity}:")
            }
            if not flat[path]:
                del flat[path]
    
    if not flat:
        print("No rules matched the criteria.", file=sys.stderr)
        return 1
    
    # Output
    print("# Code Review Rules")
    print("# Severity: C=Critical, M=Major, m=Minor")
    print()
    
    for path, rules in sorted(flat.items()):
        print(f"## {path}")
        for rule_id, rule_text in sorted(rules.items()):
            print(f"{rule_id}: {rule_text}")
        print()
    
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show statistics about the document."""
    md_path = Path(args.file)
    
    if not md_path.exists():
        print(f"Error: File not found: {md_path}", file=sys.stderr)
        return 1
    
    content = md_path.read_text(encoding="utf-8")
    result = parse_document(content)
    
    if result.errors:
        print(f"Warning: Document has {len(result.errors)} validation error(s)")
        print()
    
    stats = get_stats(result)
    
    print(f"Document: {md_path.name}")
    print(f"Source hash: {result.source_hash}")
    print()
    print(f"Total Rules: {stats['total_rules']}")
    print()
    print("By Severity:")
    print(f"  Critical (C): {stats['by_severity']['C']}")
    print(f"  Major (M):    {stats['by_severity']['M']}")
    print(f"  Minor (m):    {stats['by_severity']['m']}")
    print()
    print("By Section:")
    for path, count in sorted(stats["by_section"].items()):
        print(f"  {path}: {count}")
    
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Standards Document Sync Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate YAML from MD")
    gen_parser.add_argument("file", help="Path to markdown file")
    gen_parser.add_argument("-o", "--output", help="Output YAML path (default: <file>.rules.yml)")
    gen_parser.set_defaults(func=cmd_generate)
    
    # Validate command
    val_parser = subparsers.add_parser("validate", help="Validate MD structure")
    val_parser.add_argument("file", help="Path to markdown file")
    val_parser.set_defaults(func=cmd_validate)
    
    # Check command
    chk_parser = subparsers.add_parser("check", help="Check if YAML is up-to-date")
    chk_parser.add_argument("file", help="Path to markdown file")
    chk_parser.set_defaults(func=cmd_check)
    
    # Extract command
    ext_parser = subparsers.add_parser("extract", help="Extract rules for AI")
    ext_parser.add_argument("file", help="Path to markdown file")
    ext_parser.add_argument("--section", help="Filter by section path (e.g., python.security)")
    ext_parser.add_argument("--severity", choices=["C", "M", "m"], help="Filter by severity")
    ext_parser.set_defaults(func=cmd_extract)
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show document statistics")
    stats_parser.add_argument("file", help="Path to markdown file")
    stats_parser.set_defaults(func=cmd_stats)
    
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
