from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, TypedDict, assert_never, cast

import chevron  # type: ignore
import equation_symbolic_input_adapter
import prairielearn as pl  # type: ignore
import prairielearn.sympy_utils as psu  # type: ignore
import sympy
from lxml import html
from sympy.core.relational import Relational
from sympy.polys.polyerrors import ExactQuotientFailed, PolynomialError

_HERE: Final = Path(__file__).resolve().parent
_TEMPLATE_NAMES: Final = {
    "question": "pl-equation-input-question.mustache",
    "answer": "pl-equation-input-answer.mustache",
    "submission": "pl-equation-input-submitted.mustache",
}
_DEFAULT_SIZE: Final = 35
_DEFAULT_PLACEHOLDER: Final = "equation"
_DEFAULT_WEIGHT: Final = 1
_DEFAULT_COMPONENT_WEIGHT: Final = 1
_SYMPY_TIMEOUT: Final = 3

type RelationOperator = Literal["=", "<", "<=", ">", ">="]
type GradingMethod = Literal["exact", "equivalent", "component", "none"]
type ComponentWeights = tuple[int, int, int]
type Display = Literal["inline", "block"]

_GRADING_METHODS: Final[frozenset[str]] = frozenset(
    ("exact", "equivalent", "component", "none")
)


class RelationJson(TypedDict):
    _type: Literal["pl-equation-input"]
    operator: RelationOperator
    lhs: psu.SympyJson
    rhs: psu.SympyJson


@dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    name: str
    correct_attribute: str | None
    variables: tuple[str, ...]
    allow_inequalities: bool
    grading: GradingMethod
    lhs_weight: int
    operator_weight: int
    rhs_weight: int
    weight: int
    label: str | None
    placeholder: str
    size: int
    formula_editor: bool
    display: Display

    @property
    def component_weights(self) -> ComponentWeights:
        return self.lhs_weight, self.operator_weight, self.rhs_weight


def _split_relation(
    source: str, *, allow_inequalities: bool
) -> tuple[str, RelationOperator, str]:
    normalized = source.replace("≤", "<=").replace("≥", ">=")
    normalized = re.sub(r"\\le(?:q|qslant)?(?![A-Za-z])", "<=", normalized)
    normalized = re.sub(r"\\ge(?:q|qslant)?(?![A-Za-z])", ">=", normalized)
    normalized = re.sub(r"\\lt(?![A-Za-z])", "<", normalized)
    normalized = re.sub(r"\\gt(?![A-Za-z])", ">", normalized)
    matches = list(re.finditer(r"<=|>=|=|<|>", normalized))
    if len(matches) != 1:
        relation_example_signs = " ".join(
            f"<code>{x}</code>" for x in ["&gt;", "&lt;=", "="]
        )
        expected = (
            f"relation sign (e.g. {relation_example_signs})"
            if allow_inequalities
            else "equals sign (=)"
        )
        raise ValueError(f"The answer must contain exactly one {expected}.")
    match = matches[0]
    operator = cast(RelationOperator, match.group())
    if operator != "=" and not allow_inequalities:
        raise ValueError("Inequalities are not allowed for this input.")
    lhs, rhs = normalized[: match.start()].strip(), normalized[match.end() :].strip()
    if not lhs or not rhs:
        raise ValueError("Both sides of the relation must be nonempty.")
    return lhs, operator, rhs


def _operator(relation: Relational) -> RelationOperator:
    if isinstance(relation, sympy.Equality):
        return "="
    if isinstance(relation, sympy.StrictLessThan):
        return "<"
    if isinstance(relation, sympy.LessThan):
        return "<="
    if isinstance(relation, sympy.StrictGreaterThan):
        return ">"
    if isinstance(relation, sympy.GreaterThan):
        return ">="
    raise TypeError(f"Unsupported relation: {relation!r}")


def _relation(
    lhs: sympy.Expr, operator: RelationOperator, rhs: sympy.Expr
) -> Relational:
    constructors = {
        "=": sympy.Eq,
        "<": sympy.Lt,
        "<=": sympy.Le,
        ">": sympy.Gt,
        ">=": sympy.Ge,
    }
    return cast(Relational, constructors[operator](lhs, rhs, evaluate=False))


def _to_json(relation: Relational) -> RelationJson:
    return {
        "_type": "pl-equation-input",
        "operator": _operator(relation),
        "lhs": psu.sympy_to_json(cast(sympy.Expr, relation.lhs)),
        "rhs": psu.sympy_to_json(cast(sympy.Expr, relation.rhs)),
    }


def _from_json(value: Any) -> Relational:
    if not isinstance(value, dict) or value.get("_type") != "pl-equation-input":
        raise ValueError("Expected a pl-equation-input answer.")
    lhs = psu.json_to_sympy(value["lhs"])
    rhs = psu.json_to_sympy(value["rhs"])
    if not isinstance(lhs, sympy.Expr) or not isinstance(rhs, sympy.Expr):
        raise ValueError(  # noqa: TRY004 - malformed persisted answer
            "Both sides of an equation must be expressions."
        )
    operator = value.get("operator", "=")
    if operator not in {"=", "<", "<=", ">", ">="}:
        raise ValueError(f"Invalid relation operator: {operator!r}")
    return _relation(lhs, cast(RelationOperator, operator), rhs)


def _parse_side(source: str, variables: tuple[str, ...], side: str) -> sympy.Expr:
    result = psu.try_parse_string_as_sympy(source, variables)
    if isinstance(result, psu.SympyParseFailure):
        raise ValueError(f"The {side} side is invalid: {result.error}")  # noqa: TRY004
    if not isinstance(result.expr, sympy.Expr):
        raise ValueError(f"The {side} side must be an expression.")  # noqa: TRY004
    return result.expr


def _normalize_correct(
    value: Any, variables: tuple[str, ...], *, allow_inequalities: bool
) -> RelationJson:
    if isinstance(value, str):
        lhs_source, operator, rhs_source = _split_relation(
            value, allow_inequalities=allow_inequalities
        )
        relation = _relation(
            _parse_side(lhs_source, variables, "left"),
            operator,
            _parse_side(rhs_source, variables, "right"),
        )
    elif isinstance(value, Relational):
        relation = value
    elif isinstance(value, dict) and value.get("_type") == "pl-equation-input":
        relation = _from_json(value)
    else:
        raise ValueError(
            "The correct answer must be a relation string or SymPy relation."
        )
    if not isinstance(relation, sympy.Equality) and not allow_inequalities:
        raise ValueError('Inequalities require allow-inequalities="true".')
    return _to_json(relation)


def _config(element_html: str) -> Config:
    element = html.fragment_fromstring(element_html)
    pl.check_attribs(
        element,
        ["answers-name"],
        [
            "correct-answer",
            "variables",
            "label",
            "placeholder",
            "size",
            "weight",
            "formula-editor",
            "display",
            "allow-inequalities",
            "grading-method",
            "lhs-relative-weight",
            "operator-relative-weight",
            "rhs-relative-weight",
        ],
    )
    grading: GradingMethod | str = (
        pl.get_string_attrib(element, "grading-method", "equivalent") or "equivalent"
    )
    if grading not in _GRADING_METHODS:
        raise ValueError(
            'Attribute "grading-method" must be exact, equivalent, component, or none.'
        )

    lhs_weight, operator_weight, rhs_weight = (
        pl.get_integer_attrib(element, attribute, _DEFAULT_COMPONENT_WEIGHT)
        for attribute in (
            "lhs-relative-weight",
            "operator-relative-weight",
            "rhs-relative-weight",
        )
    )
    component_weights = lhs_weight, operator_weight, rhs_weight
    if any(weight < 0 for weight in component_weights):
        raise ValueError("Component relative weights must be nonnegative.")
    if sum(component_weights) == 0:
        raise ValueError("At least one component relative weight must be positive.")

    display = pl.get_string_attrib(element, "display", None) or "inline"
    if display not in {"inline", "block"}:
        raise ValueError('Attribute "display" must be inline or block.')

    return Config(
        name=pl.get_string_attrib(element, "answers-name"),
        correct_attribute=pl.get_string_attrib(element, "correct-answer", None),
        variables=tuple(
            psu.get_items_list(pl.get_string_attrib(element, "variables", None))
        ),
        allow_inequalities=pl.get_boolean_attrib(element, "allow-inequalities", False),
        grading=cast(GradingMethod, grading),
        lhs_weight=lhs_weight,
        operator_weight=operator_weight,
        rhs_weight=rhs_weight,
        weight=pl.get_integer_attrib(element, "weight", _DEFAULT_WEIGHT),
        label=pl.get_string_attrib(element, "label", None),
        placeholder=pl.get_string_attrib(element, "placeholder", _DEFAULT_PLACEHOLDER),
        size=pl.get_integer_attrib(element, "size", _DEFAULT_SIZE),
        formula_editor=pl.get_boolean_attrib(element, "formula-editor", False),
        display=cast(Display, display),
    )


def prepare(element_html: str, data: pl.QuestionData) -> None:
    config = _config(element_html)
    psu.validate_names_for_conflicts(
        config.name,
        list(config.variables),
        [],
        allow_complex=False,
        allow_trig_functions=True,
        allow_sets=False,
    )
    pl.check_answers_names(data, config.name)

    if config.correct_attribute is not None:
        if config.name in data["correct_answers"]:
            raise ValueError(f"duplicate correct_answers variable name: {config.name}")
        data["correct_answers"][config.name] = config.correct_attribute

    if config.name not in data["correct_answers"]:
        return
    try:
        normalized = _normalize_correct(
            data["correct_answers"][config.name],
            config.variables,
            allow_inequalities=config.allow_inequalities,
        )
    except ValueError as exc:
        raise ValueError(
            f'Parsing correct equation for "{config.name}" failed.'
        ) from exc

    data["correct_answers"][config.name] = normalized


def parse(element_html: str, data: pl.QuestionData) -> None:
    config = _config(element_html)
    data["submitted_answers"].pop(config.name, None)
    source = data["raw_submitted_answers"].get(config.name)
    if not isinstance(source, str) or not source.strip():
        data["format_errors"][config.name] = "No submitted equation."
        return

    try:
        lhs_source, operator, rhs_source = _split_relation(
            source,
            allow_inequalities=config.allow_inequalities,
        )
        relation = _relation(
            _parse_side(lhs_source, config.variables, "left"),
            operator,
            _parse_side(rhs_source, config.variables, "right"),
        )
    except ValueError as exc:
        data["format_errors"][config.name] = str(exc)
        return

    data["submitted_answers"][config.name] = _to_json(relation)


def _direction(operator: RelationOperator) -> int:
    if operator in {"<", "<="}:
        return -1
    if operator in {">", ">="}:
        return 1
    return 0


def _is_strict(operator: RelationOperator) -> bool:
    return operator in {"<", ">"}


def _reverse_operator(operator: RelationOperator) -> RelationOperator:
    reverse_operators: dict[RelationOperator, RelationOperator] = {
        "=": "=",
        "<": ">",
        "<=": ">=",
        ">": "<",
        ">=": "<=",
    }
    return reverse_operators[operator]


def _exact_match(submitted: Relational, correct: Relational) -> bool:
    submitted_lhs = cast(sympy.Expr, submitted.lhs)
    submitted_rhs = cast(sympy.Expr, submitted.rhs)
    correct_lhs = cast(sympy.Expr, correct.lhs)
    correct_rhs = cast(sympy.Expr, correct.rhs)
    correct_operator = _operator(correct)

    accepted = (
        (correct_lhs, correct_operator, correct_rhs),
        (correct_rhs, _reverse_operator(correct_operator), correct_lhs),
        (-correct_lhs, _reverse_operator(correct_operator), -correct_rhs),
        (-correct_rhs, correct_operator, -correct_lhs),
    )
    return any(
        submitted_lhs == lhs
        and _operator(submitted) == operator
        and submitted_rhs == rhs
        for lhs, operator, rhs in accepted
    )


def _component_score(
    submitted: Relational, correct: Relational, weights: ComponentWeights
) -> float:
    matches = (
        submitted.lhs == correct.lhs,
        _operator(submitted) == _operator(correct),
        submitted.rhs == correct.rhs,
    )
    earned = sum(
        weight
        for weight, matches_component in zip(weights, matches)
        if matches_component
    )
    return earned / sum(weights)


def _real_relations(
    left: Relational, right: Relational
) -> tuple[Relational, Relational, tuple[sympy.Symbol, ...]]:
    symbols = cast(
        tuple[sympy.Symbol, ...],
        tuple(
            sorted(left.free_symbols | right.free_symbols, key=sympy.default_sort_key)
        ),
    )
    replacements = {symbol: sympy.Symbol(symbol.name, real=True) for symbol in symbols}
    real_symbols = tuple(replacements[symbol] for symbol in symbols)
    return (
        cast(Relational, left.xreplace(replacements)),
        cast(Relational, right.xreplace(replacements)),
        real_symbols,
    )


def _residual(relation: Relational) -> sympy.Expr:
    return cast(sympy.Expr, cast(Any, relation.lhs) - cast(Any, relation.rhs))


def _is_proven_zero(value: sympy.Expr) -> bool:
    simplified = sympy.simplify(value)
    return simplified == 0 or simplified.equals(0) is True


def _proven_factor(left: sympy.Expr, right: sympy.Expr) -> sympy.Expr | None:
    if right == 0:
        return None
    factor = cast(sympy.Expr, sympy.cancel(cast(Any, left) / cast(Any, right)))
    if (
        getattr(factor, "is_finite", None) is not True
        or getattr(factor, "is_nonzero", None) is not True
    ):
        return None
    if not _is_proven_zero(
        cast(sympy.Expr, cast(Any, left) - cast(Any, factor) * cast(Any, right))
    ):
        return None
    return factor


def _polynomial_zero_sets_match(
    left: sympy.Expr, right: sympy.Expr, symbols: tuple[sympy.Symbol, ...]
) -> bool:
    if not symbols:
        return _is_proven_zero(left) == _is_proven_zero(right)
    try:
        left_part = sympy.Poly(left, *symbols).sqf_part()
        right_part = sympy.Poly(right, *symbols).sqf_part()
    except (PolynomialError, ValueError):  # type: ignore
        return False

    if left_part.is_zero or right_part.is_zero:
        return left_part.is_zero and right_part.is_zero

    for dividend, divisor in ((left_part, right_part), (right_part, left_part)):
        try:
            factor = cast(sympy.Expr, dividend.exquo(divisor).as_expr())
        except ExactQuotientFailed:  # type: ignore
            continue
        if (
            getattr(factor, "is_finite", None) is True
            and getattr(factor, "is_nonzero", None) is True
        ):
            return True
    return False


def _equation_zero_sets_match(
    left: Relational,
    right: Relational,
    symbols: tuple[sympy.Symbol, ...],
) -> bool:
    left_residual, right_residual = _residual(left), _residual(right)
    if _proven_factor(left_residual, right_residual) is not None:
        return True
    if _proven_factor(right_residual, left_residual) is not None:
        return True
    return _polynomial_zero_sets_match(left_residual, right_residual, symbols)


def _inequality_factor_match(left: Relational, right: Relational) -> bool:
    left_operator, right_operator = _operator(left), _operator(right)
    if _is_strict(left_operator) != _is_strict(right_operator):
        return False

    factor = _proven_factor(_residual(left), _residual(right))
    if factor is None:
        return False
    if getattr(factor, "is_positive", None) is True:
        return _direction(left_operator) == _direction(right_operator)
    if getattr(factor, "is_finite", None) is True:
        return _direction(left_operator) == -_direction(right_operator)
    return False


def _equation_inequality_match(
    equation: Relational,
    inequality: Relational,
    symbols: tuple[sympy.Symbol, ...],
) -> bool:
    operator = _operator(inequality)
    if _is_strict(operator):
        return False

    residual = _residual(inequality)
    bounds_residual_at_zero = (
        operator == "<=" and getattr(residual, "is_nonnegative", None) is True
    ) or (operator == ">=" and getattr(residual, "is_nonpositive", None) is True)
    if not bounds_residual_at_zero:
        return False

    residual_equation = _relation(residual, "=", sympy.Integer(0))
    return _equation_zero_sets_match(equation, residual_equation, symbols)


def _solution_sets_match(left: Relational, right: Relational) -> bool:
    left, right, symbols = _real_relations(left, right)

    try:
        logical_equivalence = sympy.simplify(sympy.Equivalent(left, right))
        if logical_equivalence is sympy.true:
            return True
        if not symbols:
            return logical_equivalence is sympy.false
    except (NotImplementedError, TypeError, ValueError, ZeroDivisionError):
        if not symbols:
            return False

    if len(symbols) == 1:
        try:
            left_set = sympy.solveset(left, symbols[0], domain=sympy.S.Reals)
            right_set = sympy.solveset(right, symbols[0], domain=sympy.S.Reals)
            if not isinstance(left_set, sympy.ConditionSet) and not isinstance(
                right_set, sympy.ConditionSet
            ):
                if left_set == right_set:
                    return True
                difference = sympy.simplify(
                    cast(Any, left_set).symmetric_difference(right_set)
                )
                return difference is sympy.S.EmptySet or difference == sympy.S.EmptySet
        except (NotImplementedError, TypeError, ValueError, ZeroDivisionError):
            pass

    left_is_equation = isinstance(left, sympy.Equality)
    right_is_equation = isinstance(right, sympy.Equality)
    if left_is_equation and right_is_equation:
        return _equation_zero_sets_match(left, right, symbols)
    if not left_is_equation and not right_is_equation:
        return _inequality_factor_match(left, right)
    if left_is_equation:
        return _equation_inequality_match(left, right, symbols)
    return _equation_inequality_match(right, left, symbols)


def _relation_score(
    config: Config, submitted: Relational, correct: Relational
) -> float:
    grading_method = config.grading
    match grading_method:
        case "exact":
            return float(_exact_match(submitted, correct))
        case "equivalent":
            return float(_solution_sets_match(submitted, correct))
        case "component":
            return _component_score(submitted, correct, config.component_weights)
        case "none":
            raise ValueError("An ungraded equation does not have a relation score.")
        case _:
            assert_never(grading_method)


def _relation_source(relation: Relational) -> str:
    return f"{relation.lhs} {_operator(relation)} {relation.rhs}"


def _incorrect_test_submission(
    config: Config, correct: Relational
) -> tuple[str, float]:
    correct_operator = _operator(correct)
    if correct_operator == "=":
        alternate_operator: RelationOperator = "<" if config.allow_inequalities else "="
    else:
        alternate_operator = _reverse_operator(correct_operator)
    lhs = cast(sympy.Expr, correct.lhs)
    rhs = cast(sympy.Expr, correct.rhs)
    candidates = (
        f"({lhs}) + 1 {alternate_operator} ({rhs}) + 2",
        f"({lhs}) = ({lhs})",
        f"({lhs}) = ({lhs}) + 1",
    )

    fallback: tuple[str, float] | None = None
    for source in candidates:
        submitted = _from_json(
            _normalize_correct(
                source,
                config.variables,
                allow_inequalities=config.allow_inequalities,
            )
        )
        score = _relation_score(config, submitted, correct)
        fallback = source, score
        if score < 1:
            return fallback

    # A component configuration that awards weight only to an unchangeable equals
    # sign makes every well-formed equation fully correct. Still produce a valid
    # submission and record the score that grading will return.
    assert fallback is not None
    return fallback


def grade(element_html: str, data: pl.QuestionData) -> None:
    config = _config(element_html)
    grading_method = config.grading
    if grading_method == "none":
        return
    correct_value = data["correct_answers"].get(config.name)
    if correct_value is None:
        return
    correct = _from_json(correct_value)

    def grade_function(submitted_value: Any) -> tuple[float, str | None]:
        submitted = _from_json(submitted_value)
        return _relation_score(config, submitted, correct), None

    pl.grade_answer_parameterized(
        data,
        config.name,
        grade_function,
        weight=config.weight,
        timeout=_SYMPY_TIMEOUT,
        timeout_format_error="Your relation did not converge; try a simpler form.",
    )


def test(element_html: str, data: pl.ElementTestData) -> None:
    config = _config(element_html)
    result = data["test_type"]
    correct: Relational | None = None
    if result in {"correct", "incorrect"}:
        correct_value = data["correct_answers"].get(config.name)
        if correct_value is None:
            # The element cannot construct these test cases without a correct
            # answer, so defer test submission generation to server.py.
            return
        correct = _from_json(correct_value)

    if result == "invalid":
        data["raw_submitted_answers"][config.name] = "="
        data["format_errors"][config.name] = "invalid"
        return

    assert correct is not None
    if result == "correct":
        source = _relation_source(correct)
        score: float | None = 1.0 if config.grading != "none" else None
    elif result == "incorrect":
        if config.grading == "none":
            source = f"({correct.lhs}) + 1 {_operator(correct)} {correct.rhs}"
            score = None
        else:
            source, score = _incorrect_test_submission(config, correct)
    else:
        assert_never(result)

    data["raw_submitted_answers"][config.name] = source
    if score is None:
        return
    data["partial_scores"][config.name] = {
        "score": score,
        "weight": config.weight,
    }
    pl.set_weighted_score_data(data)


def render(element_html: str, data: pl.QuestionData) -> str:
    config = _config(element_html)
    panel = data["panel"]
    correct = data.get("correct_answers", {}).get(config.name)
    if correct is not None:
        relation = _from_json(correct)
        relation_tex = sympy.latex(relation)
    else:
        relation_tex = ""

    submitted = data.get("submitted_answers", {}).get(config.name)
    submitted_relation = (
        _from_json(submitted)
        if isinstance(submitted, dict) and submitted.get("_type") == "pl-equation-input"
        else None
    )
    valid_submission = panel == "submission" and submitted_relation is not None
    if valid_submission:
        relation_tex = sympy.latex(submitted_relation)

    input_html = ""
    if panel == "question" or (panel == "submission" and not valid_submission):
        field_markup = equation_symbolic_input_adapter.markup(
            name=config.name,
            variables=config.variables,
            label=config.label,
            placeholder=config.placeholder,
            size=config.size,
            formula_editor=config.formula_editor,
            display=config.display,
        )
        input_html = equation_symbolic_input_adapter.render(
            field_markup,
            data,
            aria_label="Equation",
            submitted_answer_latex=(
                sympy.latex(submitted_relation)
                if submitted_relation is not None
                else None
            ),
        )

    params: dict[str, Any] = {
        "equation_tex": relation_tex,
        "valid_submission": valid_submission,
        "input_html": input_html,
        "label": config.label,
    }
    score = data.get("partial_scores", {}).get(config.name, {}).get("score")
    if score is not None:
        score_type, score_value = pl.determine_score_params(score)
        params[score_type] = score_value

    template = (_HERE / _TEMPLATE_NAMES[panel]).read_text(encoding="utf-8")
    return chevron.render(template, params).strip()
