import pytest
from app.errors import AppError
from app.tools.calculator import evaluate, decimal_numbers


def test_growth():
    value = evaluate('(current-previous)/previous*100', {'current':'125000000','previous':'100000000'})
    assert value['rounded_result'] == '25.00'


def test_reserve():
    assert evaluate('sales*rate/100', {'sales':'125000000','rate':'5'},0)['result'] == '6250000'


def test_decimal_not_float():
    assert evaluate('a+b', {'a':'0.1','b':'0.2'},2)['rounded_result'] == '0.30'


def test_round_half_up():
    assert evaluate('amount', {'amount':'2.345'},2)['rounded_result'] == '2.35'


def test_zero_baseline():
    with pytest.raises(AppError) as error:
        evaluate('(new-old)/old*100', {'new':'100','old':'0'})
    assert error.value.code == 'CALC_DIVISION_BY_ZERO'


@pytest.mark.parametrize('expr', ['__import__("os")', 'a.__class__', '[a][0]', 'a**100',
    'a//1','a%1','sum([a])','True','lambda: a', 'unknown+1', '125000000*5/100',
    'a;1', '{"a":a}', '(x for x in [a])'])
def test_disallowed_expressions(expr):
    with pytest.raises(AppError):
        evaluate(expr, {'a':'1'})


def test_bound():
    with pytest.raises(AppError):
        evaluate('large*large', {'large':'100000000000000000000'})


def test_expression_limit():
    with pytest.raises(AppError):
        evaluate('+'.join(['1']*70), {})


def test_numbers_preserve_persian_decimals():
    assert decimal_numbers('\u06f5\u066b\u06f2\u06f5% and 1,250,000') == ['5.25','1250000']


def test_negative_user_number():
    assert decimal_numbers('-2.5') == ['-2.5']


def test_sentence_final_number():
    assert decimal_numbers('Multiply 4 by 5.') == ['4','5']


def test_leading_decimal():
    assert decimal_numbers('Use .5 of the result.') == ['.5']
