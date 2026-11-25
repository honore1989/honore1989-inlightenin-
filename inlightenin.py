#!/usr/bin/env python3
"""A small interpreter for InLightenin programs."""

import ast
import re
import sys
from decimal import Decimal
from pathlib import Path


VARIABLE_RE = re.compile(r"Lit[1-9][0-9]*")
FUNCTION_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*[1-9][0-9]*")
SHORTCUT_RE = re.compile(r"AKA([1-9][0-9]*)")
PARAMETER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class InLighteninError(Exception):
    """An error in an InLightenin program."""


def clean_source(source):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"//.*?$", "", source, flags=re.MULTILINE)
    return re.sub(r"#.*?$", "", source, flags=re.MULTILINE)


def format_value(value):
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return format(value.quantize(Decimal(1)), "f")
        return format(value.normalize(), "f")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def evaluate_node(node, variables, line):
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        raise InLighteninError(f"Line {line}: unsupported value")

    if isinstance(node, ast.Name):
        if node.id == "true":
            return True
        if node.id == "false":
            return False
        if node.id not in variables:
            raise InLighteninError(
                f"Line {line}: undefined variable '{node.id}'"
            )
        return variables[node.id]

    if isinstance(node, ast.UnaryOp) and isinstance(
        node.op, (ast.UAdd, ast.USub)
    ):
        value = evaluate_node(node.operand, variables, line)
        if not isinstance(value, Decimal):
            raise InLighteninError(
                f"Line {line}: unary arithmetic requires a number"
            )
        return value if isinstance(node.op, ast.UAdd) else -value

    if isinstance(node, ast.BinOp):
        left = evaluate_node(node.left, variables, line)
        right = evaluate_node(node.right, variables, line)

        if isinstance(node.op, ast.Add):
            if isinstance(left, Decimal) and isinstance(right, Decimal):
                return left + right
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            raise InLighteninError(
                f"Line {line}: '+' needs two numbers or two strings"
            )

        if not isinstance(left, Decimal) or not isinstance(right, Decimal):
            raise InLighteninError(
                f"Line {line}: arithmetic requires numeric values"
            )

        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise InLighteninError(
                    f"Line {line}: division by zero"
                )
            return left / right

    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left = evaluate_node(node.left, variables, line)
        right = evaluate_node(node.comparators[0], variables, line)
        operator = node.ops[0]

        try:
            if isinstance(operator, ast.Eq):
                return left == right
            if isinstance(operator, ast.NotEq):
                return left != right
            if isinstance(operator, ast.Lt):
                return left < right
            if isinstance(operator, ast.LtE):
                return left <= right
            if isinstance(operator, ast.Gt):
                return left > right
            if isinstance(operator, ast.GtE):
                return left >= right
        except TypeError as error:
            raise InLighteninError(
                f"Line {line}: incompatible values in comparison"
            ) from error

    raise InLighteninError(f"Line {line}: unsupported expression")


def evaluate_expression(expression, variables, line):
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise InLighteninError(
            f"Line {line}: invalid expression '{expression}'"
        ) from error
    return evaluate_node(tree.body, variables, line)


def split_arguments(text, line):
    if not text.strip():
        return []

    arguments = []
    current = []
    quote = None
    escaped = False
    depth = 0

    for char in text:
        if escaped:
            current.append(char)
            escaped = False
            continue

        if char == "\\" and quote:
            current.append(char)
            escaped = True
            continue

        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue

        if char in ("'", '"'):
            quote = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            argument = "".join(current).strip()
            if not argument:
                raise InLighteninError(
                    f"Line {line}: empty function argument"
                )
            arguments.append(argument)
            current = []
        else:
            current.append(char)

    argument = "".join(current).strip()
    if not argument:
        raise InLighteninError(
            f"Line {line}: empty function argument"
        )
    arguments.append(argument)
    return arguments


def tokenize_program(source):
    """Split program text into statements and brace tokens."""
    tokens = []
    current = []
    quote = None
    escaped = False
    line = 1
    token_line = 1

    def flush():
        text = "".join(current).strip()
        if text:
            tokens.append((text, token_line))
        current.clear()

    for char in clean_source(source):
        if char == "\n":
            if quote:
                current.append(char)
            else:
                flush()
            line += 1
            if not current:
                token_line = line
            continue

        if escaped:
            current.append(char)
            escaped = False
            continue

        if char == "\\" and quote:
            current.append(char)
            escaped = True
            continue

        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue

        if char in ("'", '"'):
            if not current:
                token_line = line
            quote = char
            current.append(char)
        elif char in ("{", "}"):
            flush()
            tokens.append((char, line))
            token_line = line
        else:
            if not current and not char.isspace():
                token_line = line
            current.append(char)

    flush()
    return tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.index = 0

    def peek(self):
        if self.index < len(self.tokens):
            return self.tokens[self.index]
        return None

    def take(self):
        token = self.peek()
        if token is not None:
            self.index += 1
        return token

    def require_open_brace(self, line):
        token = self.take()
        if token is None or token[0] != "{":
            raise InLighteninError(
                f"Line {line}: expected '{{'"
            )

    def parse_block(self, opening_line):
        statements = []

        while self.peek() is not None:
            text, line = self.peek()

            if text == "}":
                self.take()
                return statements

            if text == "{":
                raise InLighteninError(
                    f"Line {line}: unexpected '{{'"
                )

            function_header = re.fullmatch(
                r"AKA\s+([A-Za-z_][A-Za-z0-9_]*[1-9][0-9]*)"
                r"\s*\((.*?)\)\s*",
                text
            )
            if function_header:
                self.take()
                name, parameter_text = function_header.groups()
                parameters = split_arguments(parameter_text, line)
                self.require_open_brace(line)
                body = self.parse_block(line)
                statements.append(
                    ("function", name, parameters, body, line)
                )
                continue

            if re.fullmatch(r"if\s*\(.*\)", text):
                statements.append(self.parse_if())
                continue

            if text.startswith("elf") or text == "else":
                raise InLighteninError(
                    f"Line {line}: 'elf' or 'else' without a matching if"
                )

            self.take()
            statements.append(("statement", text, line))

        raise InLighteninError(
            f"Line {opening_line}: missing closing '}}'"
        )

    def parse_if(self):
        text, line = self.take()
        match = re.fullmatch(r"if\s*\((.*)\)\s*", text)
        if not match:
            raise InLighteninError(
                f"Line {line}: invalid if condition"
            )

        branches = [(match.group(1), None)]
        self.require_open_brace(line)
        branches[0] = (branches[0][0], self.parse_block(line))
        otherwise = None

        while self.peek() is not None:
            next_text, next_line = self.peek()

            elf_match = re.fullmatch(r"elf\s*\((.*)\)\s*", next_text)
            if elf_match:
                self.take()
                self.require_open_brace(next_line)
                branches.append(
                    (elf_match.group(1), self.parse_block(next_line))
                )
                continue

            if next_text == "else":
                self.take()
                self.require_open_brace(next_line)
                otherwise = self.parse_block(next_line)
                break

            break

        return ("if", branches, otherwise, line)


def parse_program(source):
    # Add a synthetic outer block so parse_block handles the whole file.
    parser = Parser(tokenize_program("{\n" + source + "\n}"))
    parser.take()
    statements = parser.parse_block(1)

    if parser.peek() is not None:
        text, line = parser.peek()
        raise InLighteninError(
            f"Line {line}: unexpected '{text}'"
        )

    return statements


def execute_statements(statements, variables, functions, output, depth=0):
    if depth > 100:
        raise InLighteninError("Excessive function recursion")

    for item in statements:
        kind = item[0]

        if kind == "function":
            _, name, parameters, body, line = item
            if any(not PARAMETER_RE.fullmatch(p) for p in parameters):
                raise InLighteninError(
                    f"Line {line}: invalid function parameter"
                )
            if len(set(parameters)) != len(parameters):
                raise InLighteninError(
                    f"Line {line}: duplicate function parameter"
                )

            slot = re.search(r"([1-9][0-9]*)$", name).group(1)
            if slot in functions:
                raise InLighteninError(
                    f"Line {line}: function slot {slot} is already defined"
                )
            functions[slot] = (name, parameters, body)
            continue

        if kind == "if":
            _, branches, otherwise, line = item
            for condition, body in branches:
                if evaluate_expression(condition, variables, line):
                    execute_statements(
                        body, variables, functions, output, depth
                    )
                    break
            else:
                if otherwise is not None:
                    execute_statements(
                        otherwise, variables, functions, output, depth
                    )
            continue

        _, statement, line = item

        assignment = re.fullmatch(
            r"(Lit[1-9][0-9]*)\s*=\s*(.+)", statement
        )
        if assignment:
            name, expression = assignment.groups()
            variables[name] = evaluate_expression(
                expression, variables, line
            )
            continue

        call = re.fullmatch(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)", statement
        )
        if not call:
            raise InLighteninError(
                f"Line {line}: malformed statement '{statement}'"
            )

        callee, argument_text = call.groups()
        arguments = split_arguments(argument_text, line)

        if callee == "IN":
            if len(arguments) != 1:
                raise InLighteninError(
                    f"Line {line}: IN expects one argument"
                )
            value = evaluate_expression(arguments[0], variables, line)
            output.append(format_value(value))
            continue

        shortcut = SHORTCUT_RE.fullmatch(callee)
        if shortcut:
            slot = shortcut.group(1)
        elif FUNCTION_RE.fullmatch(callee):
            slot = re.search(r"([1-9][0-9]*)$", callee).group(1)
        else:
            raise InLighteninError(
                f"Line {line}: invalid function '{callee}'"
            )

        if slot not in functions:
            raise InLighteninError(
                f"Line {line}: function slot {slot} is not defined"
            )

        name, parameters, body = functions[slot]
        if not shortcut and callee != name:
            raise InLighteninError(
                f"Line {line}: '{callee}' does not match function '{name}'"
            )
        if len(arguments) != len(parameters):
            raise InLighteninError(
                f"Line {line}: function '{name}' expects "
                f"{len(parameters)} arguments"
            )

        local_variables = dict(variables)
        for parameter, expression in zip(parameters, arguments):
            local_variables[parameter] = evaluate_expression(
                expression, variables, line
            )

        execute_statements(
            body, local_variables, functions, output, depth + 1
        )


def execute(source):
    statements = parse_program(source)
    output = []
    execute_statements(statements, {}, {}, output)
    return output


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python3 inlightenin.py <file.inl>",
            file=sys.stderr
        )
        return 2

    try:
        source = Path(sys.argv[1]).read_text(encoding="utf-8")
        for result in execute(source):
            print(result)
        return 0
    except (InLighteninError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
