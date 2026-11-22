#!/usr/bin/env python3
"""InLightenin language interpreter."""

import re
import sys
from pathlib import Path

VARIABLE = re.compile(r"^Lit([1-9][0-9]*)$")


class InLighteninError(Exception):
    pass


def uncomment(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    return re.sub(r"#.*?$", "", text, flags=re.MULTILINE)


def parse_value(token, variables, line):
    token = token.strip()
    if not token:
        raise InLighteninError(f"Line {line}: missing value")
    if VARIABLE.fullmatch(token):
        if token not in variables:
            raise InLighteninError(f"Line {line}: undefined variable '{token}'")
        return variables[token]
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "'"):
        return token[1:-1]
    if re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", token):
        return token
    if token in ("true", "false"):
        return token
    raise InLighteninError(f"Line {line}: invalid value '{token}'")


def evaluate_expression(expression, variables, line):
    return "".join(parse_value(part, variables, line)
                   for part in expression.split("+"))


def execute(source):
    variables = {}
    output = []
    for number, raw_line in enumerate(uncomment(source).splitlines(), 1):
        statement = raw_line.strip()
        if not statement:
            continue
        assignment = re.fullmatch(
            r"(Lit[1-9][0-9]*)\s*=\s*(.+)", statement
        )
        if assignment:
            name, expression = assignment.groups()
            variables[name] = evaluate_expression(
                expression, variables, number
            )
            continue
        call = re.fullmatch(r"IN\s*\((.*)\)", statement)
        if call:
            output.append(evaluate_expression(
                call.group(1), variables, number
            ))
            continue
        raise InLighteninError(
            f"Line {number}: malformed statement '{statement}'"
        )
    return output


def main(argv):
    if len(argv) != 2:
        print("Usage: python inlightenin.py <file.inl>", file=sys.stderr)
        return 2
    try:
        for value in execute(
            Path(argv[1]).read_text(encoding="utf-8")
        ):
            print(value)
        return 0
    except (InLighteninError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))