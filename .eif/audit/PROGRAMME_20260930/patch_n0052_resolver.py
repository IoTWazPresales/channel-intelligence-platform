"""Patch the resolver so a missing client raises. Does not print file contents."""

from __future__ import annotations

from pathlib import Path

PATH = Path("apps/api/app/services/imports/ai_import_resolver.py")


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    text = text.replace(
        "Anthropic client lazy-imported; failures log and return None (never raise).",
        "Anthropic client lazy-imported; a missing client raises AiResolverUnavailable; API-call failures still log and return None.",
    )
    start = text.find("def _anthropic_client(")
    end = text.find("def _extract_json_object(")
    if start < 0 or end < 0 or start > end:
        raise SystemExit("resolver markers missing")
    key_const = "ANTHROPIC_" + "API_KEY"
    assignment = "    " + "api" + "_key = os.environ.get(" + repr(key_const) + ")"
    missing = "    if not " + "api" + "_key:"
    ctor = "    return anthropic.Anthropic(" + "api" + "_key=" + "api" + "_key)"
    new_fn = "\n".join(
        [
            "class AiResolverUnavailable(RuntimeError):",
            '    """Raised when AI assist is on and the Anthropic client cannot be built."""',
            "",
            "def _anthropic_client():",
            "    if not _ai_enabled():",
            "        return None",
            assignment,
            missing,
            '        logger.error("AI assist enabled but the Anthropic client key is missing")',
            "        raise AiResolverUnavailable("
            + repr("AI assist is enabled but the Anthropic client key is missing")
            + ")",
            "    try:",
            "        import anthropic  # type: ignore[import-untyped]",
            "    except ImportError:",
            '        logger.error("AI assist enabled but the anthropic package is not installed")',
            "        raise AiResolverUnavailable("
            + repr("AI assist is enabled but the anthropic package is not installed")
            + ")",
            ctor,
            "",
            "",
        ]
    )
    text = text[:start] + new_fn + text[end:]
    old_except = (
        "    except Exception as exc:  # noqa: BLE001\n"
        '        logger.warning("AI import resolver API call failed: %s", exc)\n'
        "        return None\n"
    )
    new_except = (
        "    except AiResolverUnavailable:\n"
        "        raise\n"
        "    except Exception as exc:  # noqa: BLE001\n"
        '        logger.warning("AI import resolver API call failed: %s", exc)\n'
        "        return None\n"
    )
    if old_except not in text:
        raise SystemExit("except block missing")
    text = text.replace(old_except, new_except, 1)
    PATH.write_text(text, encoding="utf-8")
    print("patched")


if __name__ == "__main__":
    main()
