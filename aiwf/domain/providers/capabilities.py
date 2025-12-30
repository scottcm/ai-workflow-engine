"""Provider capability definitions."""

from dataclasses import dataclass

# Valid fs_ability values
VALID_FS_ABILITIES = frozenset({"local-write", "local-read", "write-only", "none"})


@dataclass
class ProviderCapabilities:
    """Provider capabilities for prompt assembly.

    Attributes:
        fs_ability: Filesystem capability level. One of:
            - "local-write": Provider can read and write local files
            - "local-read": Provider can read local files but not write
            - "write-only": Provider can write files but not read existing ones
            - "none": Provider has no filesystem access

        supports_system_prompt: Whether the provider supports system prompts.
            This is a provider-intrinsic property determined by the AI service
            (e.g., Claude API supports system prompts, a web chat interface may not).
            Not user-configurable.

        supports_file_attachments: Whether the provider supports file attachments.
            This is a provider-intrinsic property determined by the AI service.
            Not user-configurable.
    """
    fs_ability: str
    supports_system_prompt: bool
    supports_file_attachments: bool