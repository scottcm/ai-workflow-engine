"""
Unit tests for the JPA Multi-Tenant Profile Bundle Extractor.

Contract:
- Input: Raw string from AI generation.
- Output: Dict mapping filename -> file content (as-is).
- Format:
  <<<FILE: Filename.java>>>
  [content preserved exactly as-is]
- Constraints:
  - Filenames must be .java and have no path separators.
  - No duplicates.
"""

import pytest

try:
    from profiles.jpa_mt.bundle_extractor import extract_files
except ImportError:
    extract_files = None


@pytest.fixture
def extractor():
    """Ensure extract_files is available or fail helpfully."""
    if extract_files is None:
        pytest.fail(
            "profiles.jpa_mt.bundle_extractor module or extract_files function not found."
        )
    return extract_files


def test_extract_files_single_file_happy_path(extractor):
    """Test extracting a single valid file."""
    raw_output = """<<<FILE: Product.java>>>
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
    assert "package com.example.domain;" in content
    assert "import jakarta.persistence.Entity;" in content
    assert "@Entity" in content


def test_extract_files_multiple_files_happy_path(extractor):
    """Test extracting multiple valid files from one output."""
    raw_output = """<<<FILE: Product.java>>>
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

    assert "package com.example.domain;" in files["Product.java"]
    assert "public class Product {}" in files["Product.java"]

    assert "package com.example.domain;" in files["ProductRepository.java"]
    assert "public interface ProductRepository {}" in files["ProductRepository.java"]


def test_extract_files_no_markers_raises(extractor):
    """Test that input with no markers raises ValueError."""
    raw_output = "Here is some code but no file markers.\npackage x;"

    with pytest.raises(ValueError, match="No <<<FILE:.*>>> markers found"):
        extractor(raw_output)


def test_extract_files_invalid_filename_with_path_raises(extractor):
    """Test that filenames with paths raise ValueError."""
    # Case 1: Path separator /
    with pytest.raises(ValueError, match="Invalid filename"):
        extractor("""<<<FILE: domain/Product.java>>>
package x;
""")

    # Case 2: Path separator \
    with pytest.raises(ValueError, match="Invalid filename"):
        extractor(r"""<<<FILE: domain\Product.java>>>
package x;
""")

    # Case 3: Parent directory ..
    with pytest.raises(ValueError, match="Invalid filename"):
        extractor("""<<<FILE: ../Product.java>>>
package x;
""")

    # Case 4: No .java extension
    with pytest.raises(ValueError, match="Invalid filename"):
        extractor("""<<<FILE: Product.txt>>>
package x;
""")


def test_extract_files_duplicate_filenames_raises(extractor):
    """Test that duplicate filenames raise ValueError."""
    raw_output = """<<<FILE: Product.java>>>
package x;

<<<FILE: Product.java>>>
package x;
"""
    with pytest.raises(ValueError, match="Duplicate filename"):
        extractor(raw_output)


def test_extract_files_preserves_content_as_is(extractor):
    """Test that content is preserved exactly as-is, including indentation."""
    raw_output = """<<<FILE: Product.java>>>
    package com.example;

    public class Product {
        private String name;
    }
"""
    files = extractor(raw_output)
    content = files["Product.java"]

    # Content should preserve the leading spaces
    assert "    package com.example;" in content
    assert "        private String name;" in content


def test_extract_files_with_leading_whitespace_on_marker(extractor):
    """Test that markers with leading whitespace are still matched."""
    raw_output = """
   <<<FILE: Product.java>>>
package com.example;

public class Product {}
"""
    files = extractor(raw_output)
    assert "Product.java" in files
    assert "package com.example;" in files["Product.java"]
