import ast
import re
from decimal import Decimal, DecimalException, localcontext, ROUND_HALF_UP
from ..errors import AppError

MAX_VALUE = Decimal('1e24')
DIGITS = str.maketrans('\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669', '01234567890123456789')


def decimal_numbers(text: str) -> list[str]:
    text = text.translate(DIGITS).replace('\u066b', '.').replace('\u066c', ',')
    return [m.group().replace(',', '') for m in re.finditer(
        r'(?<![\w.])[-+]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)(?!\w|\.\d)', text)]


def evaluate(expression: str, variables: dict[str, str], precision: int = 2) -> dict:
    """Only +,-,*,/ and unary signs; no eval(), calls, powers or attribute access.

    Contextual numbers must be evidence-bound names. Only 0, 1 and 100 are
    literal constants (identities and percentage conversion).
    """
    if not isinstance(expression, str) or not 1 <= len(expression) <= 256 or not 0 <= precision <= 6:
        raise AppError('CALC_INVALID', 'Invalid expression size or precision.', 422)
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, RecursionError) as exc:
        raise AppError('CALC_INVALID', 'Calculator expression is not valid arithmetic.', 422) from exc
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise AppError('CALC_LIMIT', 'Calculator expression is too complex.', 422)
    used: dict[str, str] = {}

    def bounded(value: Decimal) -> Decimal:
        if not value.is_finite() or abs(value) > MAX_VALUE:
            raise AppError('CALC_LIMIT', 'Calculator value exceeds its numeric bound.', 422)
        return value

    def visit(node) -> Decimal:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            literal = ast.get_source_segment(expression, node)
            value = Decimal(literal)
            if value not in {Decimal(0), Decimal(1), Decimal(100)}:
                raise AppError('CALC_UNGROUNDED', 'Use supplied evidence variables, not invented numeric literals.', 422)
            return value
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise AppError('CALC_UNKNOWN_VARIABLE', 'Calculator referenced an unknown evidence variable.', 422)
            used[node.id] = str(variables[node.id])
            return bounded(Decimal(str(variables[node.id])))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return bounded(left + right)
            if isinstance(node.op, ast.Sub):
                return bounded(left - right)
            if isinstance(node.op, ast.Mult):
                return bounded(left * right)
            if right == 0:
                raise AppError('CALC_DIVISION_BY_ZERO', 'Cannot divide by zero; no percentage can be reported.', 422)
            return bounded(left / right)
        raise AppError('CALC_UNSAFE', 'Only numeric variables and +, -, *, / are permitted.', 422)

    try:
        with localcontext() as context:
            context.prec = 40
            result = bounded(visit(tree))
            rounded = result.quantize(Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP)
            return {'expression': expression, 'variables': used,
                    'result': format(result, 'f'), 'rounded_result': format(rounded, 'f'),
                    'precision': precision, 'rounding': 'ROUND_HALF_UP'}
    except (DecimalException, ValueError, OverflowError) as exc:
        raise AppError('CALC_INVALID', 'Calculator inputs are outside the supported decimal range.', 422) from exc
