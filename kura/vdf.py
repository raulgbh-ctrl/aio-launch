"""Minimal parser for Valve's text KeyValues (VDF/ACF) format."""
import re

_TOKEN = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])|//[^\n]*')


def loads(text: str) -> dict:
    root: dict = {}
    stack = [root]
    key = None
    for m in _TOKEN.finditer(text):
        s, brace = m.group(1), m.group(2)
        if brace == "{":
            child: dict = {}
            if key is not None:
                stack[-1][key] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif s is not None:
            s = s.replace("\\\\", "\\").replace('\\"', '"')
            if key is None:
                key = s
            else:
                stack[-1][key] = s
                key = None
    return root


def load(path) -> dict:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return loads(f.read())
    except OSError:
        return {}
