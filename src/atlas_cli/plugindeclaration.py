from atlas_cli.atlasfiles import append_toml_section, quote_toml_string

KNOWN_PLUGINS = {
    "coding-rules": ("CODING_RULES_CANDIDATES.md", "CODING_RULES_DEVIATIONS.md"),
}


def append_plugin(text: str, name: str, source: str) -> str:
    return append_toml_section(text, f"[plugins.{name}]\nsource = {quote_toml_string(source)}\n")
