"""
Unit tests for the JPA Multi-Tenant Profile Bundle Extractor.

This test suite defines the contract for `profiles.jpa_mt.bundle_extractor`.
It enforces strict TDD by specifying expected behavior before implementation.

Contract:
- Input: Raw string from AI generation.
- Output: Dict mapping filename -> file content.
- Format:
  <<<FILE: Filename.java>>>
      package ...
      // code indented by 4 spaces
- Constraints:
  - Filenames must be .java and have no path separators.
  - Content must be indented by exactly 4 spaces (stripped in output).
  - Must have package declaration.
  - No duplicates.
  - No empty files.
"""

import pytest
try:
    from profiles.jpa_mt.bundle_extractor import extract_files
except ImportError:
    # Allow tests to be collected even if module doesn't exist yet, 
    # but they will fail when run, which is expected for TDD.
    extract_files = None


@pytest.fixture
def extractor():
    """Ensure extract_files is available or fail helpfuly."""
    if extract_files is None:
        pytest.fail("profiles.jpa_mt.bundle_extractor module or extract_files function not found. Implement it first.")
    return extract_files


def test_extract_files_single_file_happy_path(extractor):
    """Test extracting a single valid file."""
    raw_output = """
<<<FILE: Product.java>>>
    package com.example.domain;

    import jakarta.persistence.Entity;

    @Entity
    public class Product {
        // body
    }
"""
    files = extractor(raw_output)
    
    assert len(files) == 1
    assert "Product.java" in files
    
    content = files["Product.java"]
    # Verify indentation stripping
    assert content.startswith("package com.example.domain;")
    assert "    package" not in content
    assert "\nimport jakarta.persistence.Entity;" in content
    assert "\n@Entity" in content
    # Verify newlines preserved
    assert "\n\n" in content


def test_extract_files_multiple_files_happy_path(extractor):
    """Test extracting multiple valid files from one output."""
    raw_output = """
<<<FILE: Product.java>>>
    package com.example.domain;

    public class Product {}

<<<FILE: ProductRepository.java>>>
    package com.example.domain;

    public interface ProductRepository {}
"""
    files = extractor(raw_output)
    
    assert len(files) == 2
    assert "Product.java" in files
    assert "ProductRepository.java" in files
    
    product = files["Product.java"]
    assert "package com.example.domain;" in product
    assert "public class Product {}" in product
    
    repo = files["ProductRepository.java"]
    assert "package com.example.domain;" in repo
    assert "public interface ProductRepository {}" in repo


def test_extract_files_no_markers_raises(extractor):
    """Test that input with no markers raises ValueError."""
    raw_output = "Here is some code but no file markers.\n    package x;"
    
    with pytest.raises(ValueError, match="No <<<FILE:.*>>> markers found"):
        extractor(raw_output)


def test_extract_files_invalid_filename_with_path_raises(extractor):
    """Test that filenames with paths or missing extension raise ValueError."""
    # Case 1: Path separator /
    with pytest.raises(ValueError, match="Invalid filename"):
        extractor("""
<<<FILE: domain/Product.java>>>
    package x;
"""
        )
        
    # Case 2: Path separator \
    with pytest.raises(ValueError, match="Invalid filename"):
        extractor(r"""
<<<FILE: domain\Product.java>>>
    package x;
"""
        )

    # Case 3: Parent directory ..
    with pytest.raises(ValueError, match="Invalid filename"):
        extractor("""
<<<FILE: ../Product.java>>>
    package x;
"""
        )

    # Case 4: No .java extension
    with pytest.raises(ValueError, match="Invalid filename"):
        extractor("""
<<<FILE: Product.txt>>>
    package x;
"""
        )


def test_extract_files_empty_block_raises(extractor):
    """Test that a file marker with no content raises ValueError."""
    raw_output = """
<<<FILE: Product.java>>>
<<<FILE: Other.java>>>
    package x;
"""
    with pytest.raises(ValueError, match="Empty file block"):
        extractor(raw_output)
        
    # Case: Empty at end of file
    raw_output_eof = """
<<<FILE: Product.java>>>
    package x;
<<<FILE: Empty.java>>>
"""
    with pytest.raises(ValueError, match="Empty file block"):
        extractor(raw_output_eof)


def test_extract_files_incorrect_indentation_raises(extractor):
    """Test that lines with incorrect indentation raise ValueError."""
    # Case 1: 2 spaces
    with pytest.raises(ValueError, match="Incorrect indentation"):
        extractor("""
<<<FILE: Product.java>>>
  package x;
"""
        )

    # Case 2: 3 spaces
    with pytest.raises(ValueError, match="Incorrect indentation"):
        extractor("""
<<<FILE: Product.java>>>
   package x;
"""
        )

    # Case 3: 5 spaces
    with pytest.raises(ValueError, match="Incorrect indentation"):
        extractor("""
<<<FILE: Product.java>>>
     package x;
"""
        )
        
    # Case 4: No indentation
    with pytest.raises(ValueError, match="Incorrect indentation"):
        extractor("""
<<<FILE: Product.java>>>
package x;
"""
        )


def test_extract_files_missing_package_declaration_raises(extractor):
    """Test that extracted content without a package declaration raises ValueError."""
    # Valid indentation, but no package
    raw_output = """
<<<FILE: Product.java>>>
    public class Product {
    }
"""
    with pytest.raises(ValueError, match="Missing package declaration"):
        extractor(raw_output)


def test_extract_files_duplicate_filenames_raises(extractor):
    """Test that duplicate filenames raise ValueError."""
    raw_output = """
<<<FILE: Product.java>>>
    package x;
    
<<<FILE: Product.java>>>
    package x;
"""
    with pytest.raises(ValueError, match="Duplicate filename"):
        extractor(raw_output)


def test_extract_files_robustness(extractor):
    """Test robustness: whitespace around markers, blank lines, etc."""
    # Whitespace around markers
    raw_output = """
   <<<FILE: Product.java>>>   
    package com.example;
    
    
    public class Product {
        // Trailing whitespace on next line allowed? 
        // We expect code lines to start with exactly 4 spaces. 
        // Trailing spaces after code are preserved.
    }    
"""
    files = extractor(raw_output)
    assert "Product.java" in files
    content = files["Product.java"]
    
    assert "package com.example;" in content
    assert "public class Product {" in content
    # Blank lines preserved
    assert "\n\n" in content
    # Trailing spaces preserved
    assert "}    " in content
