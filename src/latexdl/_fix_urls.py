from __future__ import annotations

import re

LINK_COMMANDS = ["href", "url"]


def _fix_urls(content):
    """
    Fix URLs in the given content by escaping '%' characters in links.

    Args:
        content (str): The input string containing LaTeX content.

    Returns:
        str: The content with fixed URLs.
    """

    def replace_url(match):
        command = match.group(1)
        url = match.group(2)
        fixed_url = url.replace("%", r"\%")
        return f"\\{command}{{{fixed_url}}}"

    pattern = r"\\(" + "|".join(LINK_COMMANDS) + r")\{([^}]*)\}"
    return re.sub(pattern, replace_url, content)


def _fix_brackets(content):
    """
    Fix unmatched brackets in the given content.

    Args:
        content (str): The input string containing LaTeX content.

    Returns:
        str: The content with fixed brackets.
    """

    def encapsulate_bad_brackets(match):
        text = match.group(0)
        stack = []
        result = []
        current = ""

        for char in text:
            if char in "([":
                if current:
                    result.append(current)
                current = char
                stack.append(char)
            elif char in ")]":
                if stack and (
                    (stack[-1] == "(" and char == ")")
                    or (stack[-1] == "[" and char == "]")
                ):
                    stack.pop()
                    current += char
                    if not stack:
                        result.append(current)
                        current = ""
                else:
                    if current:
                        result.append(f"{{{current}{char}}}")
                        current = ""
                    else:
                        result.append(f"{{{char}}}")
            else:
                current += char

        if current:
            result.append(current)

        return "".join(result)

    pattern = r"\([^\(\)]*\)|\[[^\[\]]*\]"
    return re.sub(pattern, encapsulate_bad_brackets, content)


def fix_latex_document(content):
    """
    Fix URLs and brackets in the given LaTeX content.

    Args:
        content (str): The input string containing LaTeX content.

    Returns:
        str: The fixed LaTeX content.
    """
    content = _fix_urls(content)
    content = _fix_brackets(content)
    return content
