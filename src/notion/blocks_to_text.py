"""
Convert Notion block objects to plain text.
Handles common block types: paragraph, heading, bulleted/numbered list,
toggle, quote, code, callout, to_do, divider, etc.
Recursively processes child blocks.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.notion.client import paginate_blocks
from src.utils.logger import get_logger

logger = get_logger("notion.blocks_to_text")


def _rich_text_to_str(rich_text: List[Dict]) -> str:
    """Extract plain text from a rich_text array."""
    return "".join(rt.get("plain_text", "") for rt in rich_text)


def _block_to_text(block: Dict[str, Any], depth: int = 0) -> str:
    """Convert a single block to text, with optional indentation for nested."""
    btype = block.get("type", "")
    indent = "  " * depth
    content = block.get(btype, {})

    if not isinstance(content, dict):
        return ""

    rich = content.get("rich_text", [])
    text = _rich_text_to_str(rich)

    if btype == "paragraph":
        return f"{indent}{text}" if text else ""
    elif btype in ("heading_1", "heading_2", "heading_3"):
        level = btype[-1]
        prefix = "#" * int(level)
        return f"{indent}{prefix} {text}"
    elif btype == "bulleted_list_item":
        return f"{indent}• {text}"
    elif btype == "numbered_list_item":
        return f"{indent}1. {text}"
    elif btype == "to_do":
        checked = content.get("checked", False)
        mark = "[x]" if checked else "[ ]"
        return f"{indent}{mark} {text}"
    elif btype == "toggle":
        return f"{indent}▶ {text}"
    elif btype == "quote":
        return f"{indent}> {text}"
    elif btype == "callout":
        emoji = content.get("icon", {}).get("emoji", "")
        return f"{indent}{emoji} {text}".strip()
    elif btype == "code":
        lang = content.get("language", "")
        return f"{indent}```{lang}\n{text}\n```"
    elif btype == "divider":
        return f"{indent}---"
    elif btype == "equation":
        expr = content.get("expression", "")
        return f"{indent}$$ {expr} $$"
    elif btype in ("image", "video", "file", "pdf"):
        url = (
            content.get("external", {}).get("url", "")
            or content.get("file", {}).get("url", "")
        )
        caption_rich = content.get("caption", [])
        caption = _rich_text_to_str(caption_rich)
        return f"{indent}[{btype}: {caption or url}]"
    elif btype == "bookmark":
        url = content.get("url", "")
        caption_rich = content.get("caption", [])
        caption = _rich_text_to_str(caption_rich)
        return f"{indent}[bookmark: {caption or url}]"
    elif btype == "table_row":
        cells = content.get("cells", [])
        cell_texts = [_rich_text_to_str(c) for c in cells]
        return f"{indent}| " + " | ".join(cell_texts) + " |"
    elif btype == "child_page":
        title = content.get("title", "")
        return f"{indent}[child page: {title}]"
    elif btype == "column_list":
        return ""  # children handled separately
    elif btype == "column":
        return ""  # children handled separately
    else:
        # Generic fallback: try to extract rich_text
        if text:
            return f"{indent}{text}"
        return ""


def blocks_to_text(blocks: List[Dict[str, Any]], depth: int = 0, fetch_children: bool = True) -> str:
    """
    Recursively convert a list of blocks to a single text string.

    Parameters
    ----------
    blocks : list of Notion block objects
    depth : indentation depth for nested blocks
    fetch_children : if True, fetch child blocks via API when has_children=True
    """
    lines: List[str] = []

    for block in blocks:
        line = _block_to_text(block, depth=depth)
        if line:
            lines.append(line)

        # Recurse into children
        if block.get("has_children") and fetch_children:
            try:
                child_blocks = paginate_blocks(block["id"])
                child_text = blocks_to_text(child_blocks, depth=depth + 1, fetch_children=True)
                if child_text:
                    lines.append(child_text)
            except Exception as e:
                logger.warning(f"Failed to fetch children for block {block.get('id')}: {e}")

    return "\n".join(line for line in lines if line)
