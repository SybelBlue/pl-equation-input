from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest  # type: ignore
import sympy
from lxml import html as lxml_html


def _load_module():
    path = Path(__file__).resolve().parents[1] / "pl-equation-input.py"
    spec = importlib.util.spec_from_file_location("pl_equation_input", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _html(extra: str = "") -> str:
    return (
        '<pl-equation-input answers-name="eq" variables="x, y" '
        f'correct-answer="x + 1 = y" {extra}></pl-equation-input>'
    )


def _data() -> dict:
    return {
        "answers_names": {},
        "correct_answers": {},
        "submitted_answers": {},
        "raw_submitted_answers": {},
        "format_errors": {},
        "partial_scores": {},
        "panel": "question",
        "editable": True,
    }


def _submit(data: dict, name: str, value: str) -> None:
    data["raw_submitted_answers"][name] = value
    data["submitted_answers"][name] = value


def _answer_state(data: dict) -> dict:
    return {
        key: deepcopy(data[key])
        for key in (
            "answers_names",
            "correct_answers",
            "submitted_answers",
            "raw_submitted_answers",
            "format_errors",
            "partial_scores",
        )
    }


def _score(
    mod,
    submission: str,
    extra: str = "",
    *,
    correct: str = "x + 1 = y",
    variables: str = "x, y",
) -> float:
    html = (
        f'<pl-equation-input answers-name="eq" variables="{variables}" '
        f'correct-answer="{correct}" {extra}></pl-equation-input>'
    )
    data = _data()
    mod.prepare(html, data)
    _submit(data, "eq", submission)
    mod.parse(html, data)
    mod.grade(html, data)
    return data["partial_scores"]["eq"]["score"]


def _inequality_score(mod, submission: str, extra: str = "") -> float:
    html = (
        '<pl-equation-input answers-name="ineq" variables="x, y" '
        'correct-answer="x + 1 &lt; y" allow-inequalities="true" '
        f"{extra}></pl-equation-input>"
    )
    data = _data()
    mod.prepare(html, data)
    _submit(data, "ineq", submission)
    mod.parse(html, data)
    mod.grade(html, data)
    return data["partial_scores"]["ineq"]["score"]


def test_prepare_normalizes_only_the_canonical_correct_answer():
    mod = _load_module()
    data = _data()

    mod.prepare(_html(), data)

    assert data["correct_answers"]["eq"]["_type"] == "pl-equation-input"
    assert data["correct_answers"]["eq"]["lhs"]["_value"] == "x + 1"
    assert set(data["answers_names"]) == {"eq"}
    assert set(data["correct_answers"]) == {"eq"}


def test_prepare_accepts_server_sympy_equation():
    mod = _load_module()
    data = _data()
    x, y = sympy.symbols("x y")
    data["correct_answers"]["eq"] = sympy.Eq(y, 2 * x + 1, evaluate=False)
    html = '<pl-equation-input answers-name="eq" variables="x, y"></pl-equation-input>'

    mod.prepare(html, data)

    assert data["correct_answers"]["eq"]["lhs"]["_value"] == "y"
    assert data["correct_answers"]["eq"]["rhs"]["_value"] == "2*x + 1"


@pytest.mark.parametrize("answer", ["x + 1", "x = y = 1", "= x", "x ="])
def test_prepare_rejects_invalid_correct_equations(answer: str):
    mod = _load_module()
    data = _data()
    html = f'<pl-equation-input answers-name="eq" variables="x" correct-answer="{answer}" />'

    with pytest.raises(ValueError, match="Parsing correct equation"):
        mod.prepare(html, data)


def test_prepare_rejects_non_equation_server_answer():
    mod = _load_module()
    data = _data()
    data["correct_answers"]["eq"] = sympy.Symbol("x") + 1  # type: ignore

    with pytest.raises(ValueError, match="Parsing correct equation"):
        mod.prepare('<pl-equation-input answers-name="eq" variables="x" />', data)


def test_prepare_accepts_inequality_when_enabled():
    mod = _load_module()
    data = _data()
    html = (
        '<pl-equation-input answers-name="ineq" variables="x, y" '
        'correct-answer="x + 1 &lt;= y" allow-inequalities="true" />'
    )

    mod.prepare(html, data)

    assert data["correct_answers"]["ineq"]["operator"] == "<="


@pytest.mark.parametrize(
    "operator",
    ["<=", "≤", r"\le", r"\leq", r"\leqslant"],
)
def test_prepare_normalizes_less_than_or_equal_spellings(operator: str):
    mod = _load_module()
    data = _data()
    html = (
        '<pl-equation-input answers-name="ineq" variables="x" '
        f'correct-answer="x {operator} 4" allow-inequalities="true" />'
    )

    mod.prepare(html, data)

    assert data["correct_answers"]["ineq"]["operator"] == "<="


def test_prepare_accepts_server_sympy_inequality_when_enabled():
    mod = _load_module()
    data = _data()
    x = sympy.Symbol("x")
    data["correct_answers"]["ineq"] = sympy.Lt(x, 4, evaluate=False)
    html = (
        '<pl-equation-input answers-name="ineq" variables="x" '
        'allow-inequalities="true" />'
    )

    mod.prepare(html, data)

    assert data["correct_answers"]["ineq"]["operator"] == "<"


@pytest.mark.parametrize(
    ("markup", "expected_raw"),
    [
        (_html(), "x + 1 = y"),
        (
            '<pl-equation-input answers-name="ineq" variables="x" '
            'correct-answer="x &lt;= 4" allow-inequalities="true" weight="2" />',
            "x <= 4",
        ),
    ],
)
def test_correct_element_test_submission_round_trips(markup: str, expected_raw: str):
    mod = _load_module()
    state = _data()
    state |= {
        "test_type": "correct",
        "score": 0,
        "feedback": {},
        "gradable": True,
    }
    mod.prepare(markup, state)

    mod.test(markup, state)
    state["submitted_answers"] = dict(state["raw_submitted_answers"])
    mod.parse(markup, state)
    mod.grade(markup, state)

    name = next(iter(state["answers_names"]))
    assert state["raw_submitted_answers"][name] == expected_raw
    assert state["format_errors"] == {}
    assert state["partial_scores"][name]["score"] == 1
    assert state["score"] == 1


def test_correct_element_test_submission_respects_none_grading():
    mod = _load_module()
    markup = _html('grading-method="none"')
    state = _data()
    state |= {
        "test_type": "correct",
        "score": 0,
        "feedback": {},
        "gradable": True,
    }
    mod.prepare(markup, state)

    mod.test(markup, state)

    assert state["raw_submitted_answers"]["eq"] == "x + 1 = y"
    assert state["partial_scores"] == {}
    assert state["score"] == 0


@pytest.mark.parametrize(
    ("extra", "expected_score"),
    [
        ('grading-method="exact"', 0),
        ('grading-method="equivalent"', 0),
        ('grading-method="component"', pytest.approx(1 / 3)),
        (
            'grading-method="component" allow-inequalities="true"',
            0,
        ),
        ('grading-method="none"', None),
    ],
)
def test_incorrect_element_test_submission_matches_grading(
    extra: str, expected_score: float | None
):
    mod = _load_module()
    markup = _html(extra)
    state = _data()
    state |= {
        "test_type": "incorrect",
        "score": 0,
        "feedback": {},
        "gradable": True,
    }
    mod.prepare(markup, state)

    mod.test(markup, state)
    raw_submission = state["raw_submitted_answers"]["eq"]
    expected_partial_scores = deepcopy(state["partial_scores"])

    state["submitted_answers"] = {"eq": raw_submission}
    state["partial_scores"] = {}
    state["score"] = 0
    mod.parse(markup, state)
    mod.grade(markup, state)

    assert state["format_errors"] == {}
    assert state["partial_scores"] == expected_partial_scores
    if expected_score is None:
        assert state["partial_scores"] == {}
    else:
        assert state["partial_scores"]["eq"]["score"] == expected_score


def test_invalid_element_test_submission_matches_parse_format_error():
    mod = _load_module()
    markup = _html()
    state = _data()
    state |= {
        "test_type": "invalid",
        "score": 0,
        "feedback": {},
        "gradable": True,
    }
    mod.prepare(markup, state)

    mod.test(markup, state)

    assert state["raw_submitted_answers"]["eq"] == "="
    assert set(state["format_errors"]) == {"eq"}
    assert state["partial_scores"] == {}

    state["submitted_answers"] = {"eq": "="}
    state["format_errors"] = {}
    mod.parse(markup, state)

    assert set(state["format_errors"]) == {"eq"}
    assert state["submitted_answers"] == {}


def test_prepare_rejects_inequality_when_disabled():
    mod = _load_module()
    data = _data()

    with pytest.raises(ValueError, match="Parsing correct equation"):
        mod.prepare(
            '<pl-equation-input answers-name="ineq" variables="x" '
            'correct-answer="x &lt; 1" />',
            data,
        )


@pytest.mark.parametrize("grading_method", ["exact", "equivalent", "component", "none"])
def test_prepare_accepts_each_grading_method(grading_method: str):
    mod = _load_module()
    mod.prepare(_html(f'grading-method="{grading_method}"'), _data())


def test_config_captures_validated_element_configuration():
    mod = _load_module()
    config = mod._config(
        _html(
            'grading-method="component" allow-inequalities="true" '
            'lhs-relative-weight="2" operator-relative-weight="0" '
            'rhs-relative-weight="3" weight="4" label="$R:$" size="42" '
            'placeholder="e.g. x = y" formula-editor="true" display="block"'
        )
    )

    assert config.name == "eq"
    assert config.correct_attribute == "x + 1 = y"
    assert config.variables == ("x", "y")
    assert config.allow_inequalities is True
    assert config.grading == "component"
    assert config.component_weights == (2, 0, 3)
    assert config.weight == 4
    assert config.label == "$R:$"
    assert config.placeholder == "e.g. x = y"
    assert config.size == 42
    assert config.formula_editor is True
    assert config.display == "block"
    assert not hasattr(config, "__dict__")
    with pytest.raises(FrozenInstanceError):
        config.size = 10  # type: ignore[misc]


def test_prepare_rejects_unknown_grading_method():
    mod = _load_module()

    with pytest.raises(
        ValueError, match="must be exact, equivalent, component, or none"
    ):
        mod.prepare(_html('grading-method="similar"'), _data())


@pytest.mark.parametrize(
    "attribute",
    ["reversed-sign-score", "strictness-mismatch-score"],
)
def test_prepare_rejects_removed_grading_attributes(attribute: str):
    mod = _load_module()

    with pytest.raises(ValueError, match=attribute):
        mod.prepare(_html(f'{attribute}="0.5"'), _data())


@pytest.mark.parametrize(
    "extra",
    [
        'lhs-relative-weight="-1"',
        'operator-relative-weight="-1"',
        'rhs-relative-weight="-1"',
    ],
)
def test_prepare_rejects_negative_component_weights(extra: str):
    mod = _load_module()

    with pytest.raises(ValueError, match="must be nonnegative"):
        mod.prepare(_html(extra), _data())


def test_prepare_rejects_all_zero_component_weights():
    mod = _load_module()
    weights = (
        'lhs-relative-weight="0" operator-relative-weight="0" rhs-relative-weight="0"'
    )

    with pytest.raises(ValueError, match="At least one.*must be positive"):
        mod.prepare(_html(weights), _data())


def test_parse_replaces_raw_placeholder_without_auxiliary_answers():
    mod = _load_module()
    data = _data()
    mod.prepare(_html(), data)
    _submit(data, "eq", "sin(x) = y + 2")

    mod.parse(_html(), data)

    combined = data["submitted_answers"]["eq"]
    assert combined["lhs"]["_value"] == "sin(x)"
    assert combined["rhs"]["_value"] == "y + 2"
    assert set(data["submitted_answers"]) == {"eq"}


def test_grade_adds_only_the_canonical_partial_score():
    mod = _load_module()
    data = _data()
    html = _html()
    mod.prepare(html, data)
    _submit(data, "eq", "x + 1 = y")

    mod.parse(html, data)
    mod.grade(html, data)

    assert set(data["submitted_answers"]) == {"eq"}
    assert set(data["partial_scores"]) == {"eq"}


def test_parse_leaves_combined_answer_unset_when_the_input_is_invalid():
    mod = _load_module()
    data = _data()
    mod.prepare(_html(), data)
    _submit(data, "eq", "x + 1")

    mod.parse(_html(), data)

    assert data["submitted_answers"] == {}
    assert set(data["format_errors"]) == {"eq"}


@pytest.mark.parametrize(
    "submission",
    ["x + 1 = y", "y = x + 1", "-x - 1 = -y", "-y = -x - 1"],
)
def test_exact_grading_accepts_side_swaps_and_simultaneous_negation(
    submission: str,
):
    mod = _load_module()
    assert _score(mod, submission, 'grading-method="exact"') == 1


@pytest.mark.parametrize("submission", ["x = y - 1", "2*x + 2 = 2*y", "x + 2 = y"])
def test_exact_grading_rejects_rearranged_scaled_or_different_relations(
    submission: str,
):
    mod = _load_module()
    assert _score(mod, submission, 'grading-method="exact"') == 0


@pytest.mark.parametrize(
    "submission",
    ["x + 1 < y", "y > x + 1", "-x - 1 > -y", "-y < -x - 1"],
)
def test_exact_inequality_grading_transforms_the_operator(submission: str):
    mod = _load_module()
    assert _inequality_score(mod, submission, 'grading-method="exact"') == 1


@pytest.mark.parametrize("submission", ["x + 1 > y", "x + 1 <= y", "y < x + 1"])
def test_exact_inequality_grading_rejects_direction_or_strictness_changes(
    submission: str,
):
    mod = _load_module()
    assert _inequality_score(mod, submission, 'grading-method="exact"') == 0


@pytest.mark.parametrize(
    "submission",
    ["x + 1 = y", "y = x + 1", "x = y - 1", "2*x + 2 = 2*y"],
)
def test_equivalent_grading_accepts_matching_solution_sets(submission: str):
    mod = _load_module()
    assert _score(mod, submission) == 1


def test_equivalent_is_the_default_grading_method():
    mod = _load_module()
    assert _score(mod, "2*x + 2 = 2*y") == 1


def test_equivalent_grading_accepts_nonlinear_equations_with_the_same_roots():
    mod = _load_module()
    assert (
        _score(
            mod,
            "(x - 1)*(x + 1) = 0",
            correct="x^2 = 1",
            variables="x",
        )
        == 1
    )


def test_equivalent_grading_accepts_scaled_inequality():
    mod = _load_module()
    assert _inequality_score(mod, "2*x + 2 < 2*y") == 1


def test_equivalent_grading_compares_solution_sets_across_relation_types():
    mod = _load_module()
    assert (
        _score(
            mod,
            "x^2 <= 0",
            'allow-inequalities="true"',
            correct="x = 0",
            variables="x",
        )
        == 1
    )


def test_equivalent_grading_accepts_proven_multivariable_equivalence():
    mod = _load_module()
    assert _score(mod, "2*x + 2 = 2*y") == 1


def test_equivalent_grading_accepts_a_proven_nonzero_multivariable_factor():
    mod = _load_module()
    assert (
        _score(
            mod,
            "x*(y^2 + 1) = 0",
            correct="x = 0",
            variables="x, y",
        )
        == 1
    )


def test_equivalent_grading_accepts_multivariable_cross_type_certificate():
    mod = _load_module()
    assert (
        _score(
            mod,
            "x^2 + y^2 <= 0",
            'allow-inequalities="true"',
            correct="x^2 + y^2 = 0",
            variables="x, y",
        )
        == 1
    )


def test_equivalent_grading_rejects_different_solution_sets():
    mod = _load_module()
    assert _score(mod, "x^2 = 4", correct="x^2 = 1", variables="x") == 0


def test_equivalent_grading_rejects_unproved_multivariable_equivalence():
    mod = _load_module()
    assert (
        _score(
            mod,
            "x^4 + y^4 = 0",
            correct="x^2 + y^2 = 0",
            variables="x, y",
        )
        == 0
    )


def test_component_grading_scores_positional_canonical_matches():
    mod = _load_module()
    assert _score(mod, "1 + x = y", 'grading-method="component"') == 1
    assert _score(mod, "y = x + 1", 'grading-method="component"') == pytest.approx(
        1 / 3
    )


def test_component_grading_scores_each_component_independently():
    mod = _load_module()
    extra = 'grading-method="component" allow-inequalities="true"'

    assert _score(mod, "x + 1 = x", extra) == pytest.approx(2 / 3)
    assert _score(mod, "x + 2 = y", extra) == pytest.approx(2 / 3)
    assert _score(mod, "x + 1 < y", extra) == pytest.approx(2 / 3)


def test_component_grading_uses_custom_and_zero_weights():
    mod = _load_module()
    extra = (
        'grading-method="component" allow-inequalities="true" '
        'lhs-relative-weight="2" operator-relative-weight="0" '
        'rhs-relative-weight="1"'
    )

    assert _score(mod, "x + 1 < x", extra) == pytest.approx(2 / 3)


def test_none_grading_parses_but_does_not_score_submission():
    mod = _load_module()
    html = _html('grading-method="none"')
    data = _data()
    mod.prepare(html, data)
    _submit(data, "eq", "x = y - 1")

    mod.parse(html, data)
    mod.grade(html, data)

    assert data["submitted_answers"]["eq"]["operator"] == "="
    assert set(data["submitted_answers"]) == {"eq"}
    assert data["partial_scores"] == {}


@pytest.mark.parametrize("grading_method", ["exact", "equivalent", "component", "none"])
def test_missing_correct_answer_remains_ungraded(grading_method: str):
    mod = _load_module()
    html = (
        '<pl-equation-input answers-name="eq" variables="x, y" '
        f'grading-method="{grading_method}"></pl-equation-input>'
    )
    data = _data()
    mod.prepare(html, data)
    _submit(data, "eq", "x = y")

    mod.parse(html, data)
    mod.grade(html, data)

    assert "eq" in data["submitted_answers"]
    assert set(data["submitted_answers"]) == {"eq"}
    assert data["partial_scores"] == {}


def test_parse_rejects_inequality_when_disabled():
    mod = _load_module()
    data = _data()
    mod.prepare(_html(), data)
    _submit(data, "eq", "x < y")

    mod.parse(_html(), data)

    assert data["submitted_answers"] == {}
    assert "Inequalities are not allowed" in data["format_errors"]["eq"]


def test_render_uses_direct_symbolic_input_markup():
    mod = _load_module()
    data = _data()
    html = _html('formula-editor="true" label="$L:$" size="42" display="block"')
    mod.prepare(html, data)

    rendered = mod.render(html, data)

    assert "<pl-symbolic-input" not in rendered
    assert 'name="eq"' in rendered
    assert "<math-field" in rendered
    assert 'aria-label="Equation"' in rendered
    assert "w-100" in rendered
    assert "$L:$" in rendered


def test_formula_editor_loads_relation_shortcut_extension_after_vendor():
    element_dir = Path(__file__).resolve().parents[1]
    info = json.loads((element_dir / "info.json").read_text())

    assert info["dependencies"]["elementScripts"] == [
        "vendor/prairielearn/pl-symbolic-input/pl-symbolic-input.js",
        "pl-equation-input.js",
    ]


def test_formula_editor_uses_equation_initializer():
    mod = _load_module()
    data = _data()
    html = _html('formula-editor="true"')
    mod.prepare(html, data)

    rendered = mod.render(html, data)

    assert "window.PLEquationInput" in rendered
    assert "window.PLSymbolicInput" not in rendered


def test_render_defaults_symbolic_input_display_to_inline():
    mod = _load_module()
    data = _data()
    html = _html()
    mod.prepare(html, data)

    rendered = mod.render(html, data)

    assert "form-control" in rendered
    assert "d-inline-block" in rendered


@pytest.mark.parametrize(
    ("formula_editor", "placeholder_attribute"),
    [(False, "placeholder"), (True, "data-placeholder-text")],
)
def test_render_uses_custom_placeholder(
    formula_editor: bool, placeholder_attribute: str
):
    mod = _load_module()
    data = _data()
    html = _html(
        f'placeholder="e.g. 2x &lt;= 7" formula-editor="{str(formula_editor).lower()}"'
    )
    mod.prepare(html, data)

    rendered = mod.render(html, data)

    rendered_element = lxml_html.fragment_fromstring(rendered)
    xpath = ".//math-field" if formula_editor else './/input[@type="text"]'
    [input_element] = rendered_element.xpath(xpath)
    assert input_element.get(placeholder_attribute) == "e.g. 2x <= 7"


def test_render_resolves_templates_from_the_element_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    mod = _load_module()
    data = _data()
    html = _html()
    mod.prepare(html, data)
    monkeypatch.chdir(tmp_path)

    rendered = mod.render(html, data)

    assert 'name="eq"' in rendered


def test_render_answer_displays_the_full_equation_as_latex():
    mod = _load_module()
    data = _data()
    html = _html('label="$L:$"')
    mod.prepare(html, data)
    data["panel"] = "answer"

    rendered = mod.render(html, data)

    assert "<pl-symbolic-input" not in rendered
    assert "$L:$" in rendered
    assert r"x + 1 = y" in rendered


def test_none_grading_still_displays_the_correct_answer():
    mod = _load_module()
    data = _data()
    html = _html('grading-method="none"')
    mod.prepare(html, data)
    data["panel"] = "answer"

    rendered = mod.render(html, data)

    assert r"x + 1 = y" in rendered


def test_render_submission_displays_the_full_submitted_equation():
    mod = _load_module()
    data = _data()
    html = _html('label="$L:$"')
    mod.prepare(html, data)
    _submit(data, "eq", "y = x + 1")
    mod.parse(html, data)
    mod.grade(html, data)
    data["panel"] = "submission"

    rendered = mod.render(html, data)

    assert "<pl-symbolic-input" not in rendered
    assert r"y = x + 1" in rendered
    assert "100%" in rendered


def test_none_grading_submission_has_no_score_badge():
    mod = _load_module()
    data = _data()
    html = _html('grading-method="none"')
    mod.prepare(html, data)
    _submit(data, "eq", "x = y - 1")
    mod.parse(html, data)
    mod.grade(html, data)
    data["panel"] = "submission"

    rendered = mod.render(html, data)

    assert r"x = y - 1" in rendered
    assert "badge" not in rendered


def test_render_full_equation_uses_an_isolated_answer_view():
    mod = _load_module()
    data = _data()
    html = (
        '<pl-equation-input answers-name="cartesian_equation" variables="x, y" '
        'correct-answer="x^2 + y^2 = 36" formula-editor="true" />'
    )
    mod.prepare(html, data)
    _submit(data, "cartesian_equation", "x^2+y^2=36")
    mod.parse(html, data)
    answers_before = _answer_state(data)

    rendered = mod.render(html, data)

    assert "<pl-symbolic-input" not in rendered
    assert 'name="cartesian_equation"' in rendered
    assert r"x^{2} + y^{2} = 36" in rendered
    assert _answer_state(data) == answers_before


def test_render_invalid_submission_uses_isolated_symbolic_input_renderer():
    mod = _load_module()
    data = _data()
    html = _html('display="block"')
    mod.prepare(html, data)
    _submit(data, "eq", "x + 1")
    mod.parse(html, data)
    data["panel"] = "submission"
    answers_before = _answer_state(data)

    rendered = mod.render(html, data)

    assert "<pl-symbolic-input" not in rendered
    assert "The answer must contain exactly one equals sign" in rendered
    assert data["submitted_answers"] == {}
    assert _answer_state(data) == answers_before
