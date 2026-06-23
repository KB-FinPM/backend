from app.core.supported_files import (
    SUPPORTED_FILE_TYPE_MESSAGE,
    supported_extensions_for_display,
)


def test_supported_file_type_message_mentions_all_display_extensions() -> None:
    message = SUPPORTED_FILE_TYPE_MESSAGE.lower()
    missing_extensions = [
        extension
        for extension in supported_extensions_for_display()
        if extension.lstrip(".").lower() not in message
    ]

    assert missing_extensions == []
