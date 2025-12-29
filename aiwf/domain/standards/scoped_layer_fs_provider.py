"""Scope-aware filesystem standards provider."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any

from aiwf.domain.errors import ProviderError


class ScopedLayerFsProvider:
    """Scope-aware filesystem standards provider.

    Selects standards files based on scope->layer mappings:
    1. Scope defines which layers are active
    2. Each layer maps to a list of standards files
    3. Files are read from filesystem and concatenated

    Timeout behavior:
        This provider only uses response_timeout. The connection_timeout
        parameter is NOT applicable for local filesystem access because
        there is no separate "connect" phase - filesystem access is
        synchronous. The default_connection_timeout is None, and any
        value passed is effectively ignored since it's combined with
        response_timeout.

        For network-based standards providers (e.g., REST API, database),
        connection_timeout would specify the time allowed to establish
        the connection before data transfer begins.

        Recommendation: Leave connection_timeout as None (the default)
        when using this filesystem provider.

    Config structure:
        {
            "standards": {"root": "/path/to/standards"},
            "scopes": {
                "domain": {"layers": ["entity", "repository"]},
                "vertical": {"layers": ["entity", "repository", "service"]}
            },
            "layer_standards": {
                "_universal": ["coding-standards.md"],
                "entity": ["entity-standards.md"],
                "repository": ["repository-standards.md"],
                "service": ["service-standards.md"]
            }
        }
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize provider with configuration.

        Args:
            config: Configuration dict with standards.root, scopes, layer_standards
        """
        self.config = config
        standards_config = config.get("standards", {})
        root_path = standards_config.get("root", "")
        self.standards_root = Path(root_path) if root_path else None
        self.scopes = config.get("scopes", {})
        self.layer_standards = config.get("layer_standards", {})

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata for discovery commands.

        Timeout notes:
            - default_connection_timeout: None for filesystem provider because
              there is no network connection phase. Local filesystem access is
              synchronous and doesn't have a separate "connect" vs "transfer" phase.
              For network-based providers (e.g., remote repositories), this would
              specify the time allowed to establish the connection.
            - default_response_timeout: 30 seconds to read and concatenate all
              standards files. Protects against hung network mounts or slow storage.
            - None or 0 means "no timeout" - operation can take unlimited time.
        """
        return {
            "name": "scoped-layer-fs",
            "description": "Scope-aware filesystem standards provider",
            "requires_config": True,
            "config_keys": ["standards.root", "scopes", "layer_standards"],
            "default_connection_timeout": None,  # N/A for local filesystem - no connection phase
            "default_response_timeout": 30,  # seconds to read all files
        }

    def validate(self) -> None:
        """Verify standards root exists and is readable.

        Raises:
            ProviderError: If provider is misconfigured or standards root is inaccessible
        """
        if not self.standards_root:
            raise ProviderError("Standards root not configured")

        if not self.standards_root.exists():
            raise ProviderError(f"Standards root not found: {self.standards_root}")

        if not self.standards_root.is_dir():
            raise ProviderError(
                f"Standards root is not a directory: {self.standards_root}"
            )

        # Verify at least one scope is configured
        if not self.scopes:
            raise ProviderError("No scopes configured")

    def create_bundle(
        self,
        context: dict[str, Any],
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        """Create standards bundle with timeout protection.

        Uses ThreadPoolExecutor to enforce timeout on file I/O operations,
        protecting against hung network mounts or slow storage.

        Args:
            context: Workflow context with 'scope' key
            connection_timeout: Timeout for connection phase in seconds.
                None or 0 means no timeout. If not specified, uses provider default.
                For filesystem provider, default is None (no connection phase).
            response_timeout: Timeout for reading all files in seconds.
                None or 0 means no timeout. If not specified, uses provider default (30s).

        Returns:
            Concatenated standards bundle as string

        Raises:
            ProviderError: If bundle creation fails or times out
            ValueError: If context is invalid (e.g., unknown scope)
        """
        # Resolve timeouts: explicit value > provider default
        # None means "use default", 0 means "no timeout"
        metadata = self.get_metadata()

        # For connection_timeout: use explicit value if provided, else default
        if connection_timeout is not None:
            conn_timeout = connection_timeout if connection_timeout > 0 else None
        else:
            default_conn = metadata["default_connection_timeout"]
            conn_timeout = default_conn if default_conn and default_conn > 0 else None

        # For response_timeout: use explicit value if provided, else default
        if response_timeout is not None:
            resp_timeout = response_timeout if response_timeout > 0 else None
        else:
            default_resp = metadata["default_response_timeout"]
            resp_timeout = default_resp if default_resp and default_resp > 0 else None

        # Calculate total timeout (only if at least one timeout is set)
        # For filesystem provider, conn_timeout is typically None
        total_timeout: float | None = None
        if conn_timeout is not None or resp_timeout is not None:
            total_timeout = (conn_timeout or 0) + (resp_timeout or 0)
            if total_timeout == 0:
                total_timeout = None  # 0 means no timeout

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._read_files, context)
            try:
                return future.result(timeout=total_timeout)
            except FuturesTimeoutError:
                raise ProviderError(
                    f"Standards read timed out after {total_timeout}s"
                )

    def _read_files(self, context: dict[str, Any]) -> str:
        """Internal method to read and concatenate standards files.

        Args:
            context: Workflow context with 'scope' key

        Returns:
            Concatenated standards bundle

        Raises:
            ValueError: If scope is unknown
            ProviderError: If standards files cannot be read
        """
        scope = None
        if isinstance(context, dict):
            scope = context.get("scope")

        if not scope or scope not in self.scopes:
            raise ValueError(f"Unknown scope: {scope}")

        layers = self.scopes[scope].get("layers", [])

        # Collect standards files preserving order:
        # 1. _universal
        # 2. layers in scope order
        # Deduplicate preserving first occurrence
        ordered_files: list[str] = []
        seen: set[str] = set()

        def add_files(file_list: list[str]) -> None:
            for f in file_list:
                if f not in seen:
                    ordered_files.append(f)
                    seen.add(f)

        if "_universal" in self.layer_standards:
            add_files(self.layer_standards["_universal"])

        for layer in layers:
            if layer in self.layer_standards:
                add_files(self.layer_standards[layer])

        # Read and concatenate
        bundle_parts = []
        for filename in ordered_files:
            file_path = self.standards_root / filename
            try:
                content = file_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                raise ProviderError(f"Standards file not found: {file_path}")
            except OSError as e:
                raise ProviderError(f"Failed to read standards file {file_path}: {e}")

            if not content.endswith("\n"):
                content += "\n"

            bundle_parts.append(f"--- {filename} ---\n{content}")

        return "".join(bundle_parts)