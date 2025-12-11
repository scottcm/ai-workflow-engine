import re

def extract_files(raw_output: str) -> dict[str, str]:
    """
    Extracts files from an AI-generated raw response string using <<<FILE: >>> markers.

    Args:
        raw_output: The raw string containing file markers and code.

    Returns:
        A dictionary mapping filenames to their stripped content.

    Raises:
        ValueError: If validation fails (invalid filename, no markers, duplicates, 
                    indentation errors, missing package, empty blocks).
    """
    
    # Relaxed regex to capture ANY filename for subsequent validation
    # Matches: start of line, <<<FILE:, filename, >>>, optional spaces, newline OR end of string
    # This ensures the newline immediately following the marker is consumed and not part of the content.
    marker_pattern = re.compile(r'^\s*<<<FILE:\s*(.+?)>>>[ \t]*(\r?\n|\Z)', re.MULTILINE)
    
    matches = list(marker_pattern.finditer(raw_output))
    
    if not matches:
        raise ValueError("No <<<FILE: ...>>> markers found in output.")
        
    files = {}
    
    for i, match in enumerate(matches):
        filename = match.group(1).strip()
        start_index = match.end()
        
        # Determine the end of the current block (start of next marker or end of string)
        if i + 1 < len(matches):
            end_index = matches[i + 1].start()
        else:
            end_index = len(raw_output)
            
        block_content = raw_output[start_index:end_index]
        
        # 1. Validate Filename
        if (not filename.endswith(".java") or 
            any(char in filename for char in ['/', '\\', ':', '..'])):
            raise ValueError(f"Invalid filename: '{filename}'. Must end in .java and contain no paths.")
            
        if filename in files:
            raise ValueError(f"Duplicate filename detected: {filename}")
            
        # 2. Process Content
        lines = block_content.splitlines()
        processed_lines = []
        has_non_blank_code = False
        
        for line in lines:
            # Skip/Preserve blank lines (which may contain whitespace but are visually empty)
            if not line.strip():
                processed_lines.append("")
                continue
            
            # 3. Validate Indentation (Strict 4 spaces base, must be multiple of 4)
            if not line.startswith("    "):
                raise ValueError(f"Incorrect indentation in '{filename}'. Line must start with exactly 4 spaces.")
            
            # Check for alignment to 4-space grid (rejects 5, 6, 7 spaces, accepts 8)
            leading_spaces = len(line) - len(line.lstrip(' '))
            if leading_spaces % 4 != 0:
                raise ValueError(f"Incorrect indentation in '{filename}'. Indentation must be a multiple of 4.")
                
            # Strip exactly 4 spaces
            content_line = line[4:]
            processed_lines.append(content_line)
            has_non_blank_code = True
            
        if not has_non_blank_code:
            raise ValueError(f"Empty file block for '{filename}'. Must contain at least one line of code.")
            
        # Join lines to form file content
        extracted_content = "\n".join(processed_lines)
        
        # 4. Validate Package Declaration
        # Look for 'package' keyword at the start of a line (allowing for potential comments/whitespace above it)
        # Simple check: the stripped content must have a line starting with 'package '
        if not re.search(r'^\s*package\s+', extracted_content, re.MULTILINE):
            raise ValueError(f"Missing package declaration in '{filename}'.")
            
        files[filename] = extracted_content
        
    return files