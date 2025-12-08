"""Phase 2 Smoke Test - Profile Configuration & Validation."""
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import shutil
import os

from aiwf.domain.validation import (
    PathValidator,
    validate_standards_root,
    validate_target_root,
)


def test_path_validator():
    """Test PathValidator basic functionality."""
    print("\n=== Testing PathValidator ===")
    
    # Test entity name sanitization
    print("1. Testing entity name sanitization...")
    clean = PathValidator.sanitize_entity_name("Product")
    assert clean == "Product"
    
    clean = PathValidator.sanitize_entity_name("Order-Item")
    assert clean == "Order-Item"
    
    try:
        PathValidator.sanitize_entity_name("../../../etc/passwd")
        assert False, "Should reject path traversal"
    except Exception as e:
        print(f"   ✓ Rejected path traversal: {e}")
    
    # Test environment variable expansion
    print("2. Testing environment variable expansion...")
    os.environ["TEST_VAR"] = "/test/path"
    expanded = PathValidator.expand_env_vars("${TEST_VAR}/subdir")
    assert expanded == "/test/path/subdir"
    print(f"   ✓ Expanded: ${{TEST_VAR}}/subdir → {expanded}")
    
    try:
        PathValidator.expand_env_vars("${UNDEFINED_VAR}/path")
        assert False, "Should reject undefined variables"
    except Exception as e:
        print(f"   ✓ Rejected undefined variable: {e}")
    
    # Test template formatting
    print("3. Testing template formatting...")
    template = "{entity}/{scope}"
    variables = {"entity": "Product", "scope": "domain"}
    result = PathValidator.format_template(template, variables, sanitize=True)
    assert result == "Product/domain"
    print(f"   ✓ Formatted: {template} → {result}")
    
    print("✅ PathValidator tests passed!\n")


def test_profile_config_loading():
    """Test JpaMtProfile config loading and validation."""
    print("\n=== Testing Profile Config Loading ===")
    
    # Create a temporary config for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create mock standards directory
        standards_dir = tmpdir_path / "standards"
        standards_dir.mkdir()
        
        # Create mock standards files
        (standards_dir / "ORG.md").write_text("# Organization Standards")
        (standards_dir / "JPA_AND_DATABASE.md").write_text("# JPA Standards")
        
        # Create test config
        config_content = f"""
standards:
  root: "{standards_dir}"

artifacts:
  session_root: ".aiwf/sessions"
  target_root: null
  target_structure: "{{entity}}/{{scope}}"
  copy_strategy:
    iterations: true
    audit_trail: true
    standards: true

scopes:
  domain:
    description: "Domain layer"
    layers: [entity, repository]
  vertical:
    description: "Full stack"
    layers: [entity, repository, service]

layer_standards:
  _universal:
    - ORG.md
  entity:
    - JPA_AND_DATABASE.md
  repository:
    - JPA_AND_DATABASE.md
  service:
    - ORG.md
"""
        
        config_file = tmpdir_path / "config.yml"
        config_file.write_text(config_content)
        
        # Test profile loading
        print("1. Testing profile initialization...")
        from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile
        
        profile = JpaMtProfile(config_path=config_file)
        assert profile.config is not None
        assert "scopes" in profile.config
        assert "domain" in profile.config["scopes"]
        print("   ✓ Profile loaded successfully")
        
        # Test standards bundling
        print("2. Testing standards bundling...")
        context = {"scope": "domain"}
        bundle = profile.standards_bundle_for(context)
        
        assert "ORG.md" in bundle
        assert "JPA_AND_DATABASE.md" in bundle
        assert "# Organization Standards" in bundle
        assert "# JPA Standards" in bundle
        print(f"   ✓ Bundle created ({len(bundle)} chars)")
        
        # Test scope validation
        print("3. Testing scope validation...")
        try:
            profile.standards_bundle_for({"scope": "invalid"})
            assert False, "Should reject invalid scope"
        except ValueError as e:
            print(f"   ✓ Rejected invalid scope: {e}")
        
        print("✅ Profile config tests passed!\n")


def test_bundle_parsing():
    """Test bundle parsing functionality."""
    print("\n=== Testing Bundle Parsing ===")
    
    from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile
    
    # Create minimal profile for testing (no config needed for parse_bundle)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        standards_dir = tmpdir_path / "standards"
        standards_dir.mkdir()
        
        config = {
            "standards": {"root": str(standards_dir)},
            "artifacts": {
                "session_root": ".aiwf/sessions",
                "target_root": None,
                "target_structure": "{entity}/{scope}",
                "copy_strategy": {"iterations": True, "audit_trail": True, "standards": True}
            },
            "scopes": {"domain": {"layers": []}},
            "layer_standards": {}
        }
        
        profile = JpaMtProfile(**config)
        
        # Test bundle format
        print("1. Testing bundle parsing...")
        bundle_content = """
<<<FILE: Product.java>>>
    package com.example;
    
    public class Product {
        private String name;
    }

<<<FILE: ProductRepository.java>>>
    package com.example;
    
    public interface ProductRepository {
        Product findByName(String name);
    }
"""
        
        files = profile.parse_bundle(bundle_content)
        assert len(files) == 2
        assert "Product.java" in files
        assert "ProductRepository.java" in files
        assert "package com.example;" in files["Product.java"]
        assert "public class Product" in files["Product.java"]
        print(f"   ✓ Parsed {len(files)} files")
        
        # Test empty bundle rejection
        print("2. Testing empty bundle rejection...")
        try:
            profile.parse_bundle("No files here")
            assert False, "Should reject empty bundle"
        except ValueError as e:
            print(f"   ✓ Rejected empty bundle: {e}")
        
        print("✅ Bundle parsing tests passed!\n")


def test_artifact_dir_resolution():
    """Test artifact directory resolution."""
    print("\n=== Testing Artifact Directory Resolution ===")
    
    from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        standards_dir = tmpdir_path / "standards"
        standards_dir.mkdir()
        
        # Test without target_root
        print("1. Testing without target_root...")
        config = {
            "standards": {"root": str(standards_dir)},
            "artifacts": {
                "session_root": ".aiwf/sessions",
                "target_root": None,
                "target_structure": "{entity}/{scope}",
                "copy_strategy": {"iterations": True, "audit_trail": True, "standards": True}
            },
            "scopes": {"domain": {"layers": []}},
            "layer_standards": {}
        }
        
        profile = JpaMtProfile(**config)
        artifact_dir = profile.artifact_dir_for("Product", "domain")
        assert artifact_dir == Path("artifacts")
        print(f"   ✓ Returns relative path: {artifact_dir}")
        
        # Test with target_root
        print("2. Testing with target_root...")
        target_dir = tmpdir_path / "target"
        target_dir.mkdir()
        
        config["artifacts"]["target_root"] = str(target_dir)
        profile = JpaMtProfile(**config)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        artifact_dir = profile.artifact_dir_for(
            "Product", 
            "domain",
            session_id=f"session-{timestamp}",
            timestamp=timestamp
        )
        
        assert str(target_dir) in str(artifact_dir)
        assert "Product" in str(artifact_dir)
        assert "domain" in str(artifact_dir)
        print(f"   ✓ Resolved to: {artifact_dir}")
        
        print("✅ Artifact directory tests passed!\n")


def main():
    """Run all Phase 2 smoke tests."""
    print("\n" + "="*60)
    print("PHASE 2 SMOKE TEST")
    print("="*60)
    
    try:
        test_path_validator()
        test_profile_config_loading()
        test_bundle_parsing()
        test_artifact_dir_resolution()
        
        print("\n" + "="*60)
        print("✅ ALL PHASE 2 SMOKE TESTS PASSED!")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()