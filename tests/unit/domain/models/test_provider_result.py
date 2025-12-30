"""Tests for ProviderResult model."""

from aiwf.domain.models.provider_result import ProviderResult


class TestProviderResultFields:
    """Tests for ProviderResult field definitions."""

    def test_empty_result(self) -> None:
        """Can create with no arguments - all fields have defaults."""
        result = ProviderResult()
        assert result.files == {}
        assert result.response is None

    def test_files_with_content(self) -> None:
        """Files can contain content strings for non-writing providers."""
        result = ProviderResult(
            files={
                "entity/Customer.java": "public class Customer {}",
                "entity/Order.java": "public class Order {}",
            }
        )
        assert result.files["entity/Customer.java"] == "public class Customer {}"
        assert result.files["entity/Order.java"] == "public class Order {}"

    def test_files_with_none_values(self) -> None:
        """Files can have None values for providers that write directly."""
        result = ProviderResult(
            files={
                "entity/Customer.java": None,
                "entity/Order.java": None,
            }
        )
        assert result.files["entity/Customer.java"] is None
        assert result.files["entity/Order.java"] is None

    def test_mixed_files(self) -> None:
        """Files can mix content and None values."""
        result = ProviderResult(
            files={
                "entity/Customer.java": None,  # Provider wrote this
                "summary.md": "# Summary\nGenerated 2 entities",  # Engine should write this
            }
        )
        assert result.files["entity/Customer.java"] is None
        assert result.files["summary.md"] == "# Summary\nGenerated 2 entities"

    def test_response_optional_commentary(self) -> None:
        """Response field holds optional commentary."""
        result = ProviderResult(
            files={"Foo.java": "class Foo {}"},
            response="Generated Foo class with standard patterns",
        )
        assert result.response == "Generated Foo class with standard patterns"


class TestProviderResultContract:
    """Tests verifying model contract for external callers."""

    def test_model_fields_exist(self) -> None:
        """All documented fields exist on the model."""
        expected_fields = {"files", "response"}
        assert expected_fields == set(ProviderResult.model_fields.keys())

    def test_files_is_mutable_dict(self) -> None:
        """Files dict can be modified after creation."""
        result = ProviderResult()
        result.files["new_file.java"] = "content"
        assert "new_file.java" in result.files

    def test_files_default_is_independent(self) -> None:
        """Each instance gets its own files dict (not shared)."""
        result1 = ProviderResult()
        result2 = ProviderResult()
        result1.files["only_in_result1.java"] = "content"
        assert "only_in_result1.java" not in result2.files


class TestProviderResultUsagePatterns:
    """Tests demonstrating expected usage patterns from ADR."""

    def test_local_write_capable_provider(self) -> None:
        """Providers like Claude Code return None for all files."""
        result = ProviderResult(
            files={
                "entity/Customer.java": None,
                "entity/Order.java": None,
                "repository/CustomerRepository.java": None,
            }
        )
        assert all(v is None for v in result.files.values())

    def test_non_writing_provider(self) -> None:
        """Web chat/API providers return content for all files."""
        result = ProviderResult(
            files={
                "entity/Customer.java": "public class Customer { /* ... */ }",
                "entity/Order.java": "public class Order { /* ... */ }",
            }
        )
        assert all(isinstance(v, str) for v in result.files.values())

    def test_subdirectory_support(self) -> None:
        """File paths can include subdirectories."""
        result = ProviderResult(
            files={
                "entity/Customer.java": "content",
                "repository/CustomerRepository.java": "content",
                "service/CustomerService.java": "content",
            }
        )
        paths = list(result.files.keys())
        assert "entity/Customer.java" in paths
        assert "repository/CustomerRepository.java" in paths
        assert "service/CustomerService.java" in paths