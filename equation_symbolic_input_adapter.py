"""Isolated rendering bridge to the vendored PrairieLearn symbolic input."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, cast

import lxml.html
import prairielearn as pl

HERE = Path(__file__).parent
VENDOR_DIR = HERE / "vendor" / "prairielearn" / "pl-symbolic-input"
CONTROLLER_PATH = VENDOR_DIR / "pl-symbolic-input.py"
TEMPLATE_PATH = VENDOR_DIR / "pl-symbolic-input.mustache"


def _load_controller() -> ModuleType:
    module_name = "pl_equation_input_vendored_symbolic_input"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, CONTROLLER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load vendored controller at {CONTROLLER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    # Upstream normally runs with the element directory as its working directory.
    # Use an absolute template path so this adapter does not mutate process-global cwd.
    module.SYMBOLIC_INPUT_MUSTACHE_TEMPLATE_NAME = str(TEMPLATE_PATH)  # type: ignore
    return module


CONTROLLER = _load_controller()


def markup(
    *,
    name: str,
    variables: tuple[str, ...],
    label: str | None,
    placeholder: str,
    size: int,
    formula_editor: bool,
    display: Literal["inline", "block"],
) -> str:
    element = lxml.html.Element("pl-symbolic-input")
    attributes = {
        "answers-name": name,
        "variables": ",".join(variables),
        "formula-editor": str(formula_editor).lower(),
        "show-score": "false",
        "weight": "0",
        "placeholder": placeholder,
        "size": str(size),
        "aria-label": "Equation",
        "display": display,
    }
    if label is not None:
        attributes["label"] = label
    for key, value in attributes.items():
        element.set(key, value)
    return cast(str, lxml.html.tostring(element, encoding="unicode"))


def _render_data_view(
    data: dict[str, Any] | pl.QuestionData, name: str
) -> dict[str, Any]:
    view = dict(data)
    format_errors = dict(data.get("format_errors", {}))
    view["correct_answers"] = {}
    view["format_errors"] = format_errors
    view["partial_scores"] = {}
    view["raw_submitted_answers"] = dict(data.get("raw_submitted_answers", {}))
    # pl-symbolic-input treats a missing submitted answer as an ordinary blank field,
    # but it needs the key to be present to display an associated format error. Never
    # expose the equation relation JSON (or PrairieLearn's raw string placeholder) to
    # its expression decoder.
    view["submitted_answers"] = {name: None} if name in format_errors else {}
    view.setdefault("panel", "question")
    view.setdefault("editable", view["panel"] == "question")
    return view


def render(
    field_markup: str,
    data: pl.QuestionData,
    *,
    aria_label: str,
    submitted_answer_latex: str | None = None,
) -> str:
    element = lxml.html.fragment_fromstring(field_markup)
    name = element.get("answers-name")
    if not name:
        raise ValueError("Delegated symbolic input is missing answers-name.")
    view = _render_data_view(data, name)
    if submitted_answer_latex is not None:
        view["raw_submitted_answers"].setdefault(
            f"{name}-latex", submitted_answer_latex
        )
    rendered = CONTROLLER.render(field_markup, view)
    # The pinned upstream formula-editor template does not apply its aria-label
    # parameter to the math-field. Keep the vendored files pristine and bridge
    # that accessibility gap in the adapter.
    rendered = rendered.replace(
        "<math-field", f'<math-field aria-label="{aria_label}"', 1
    )
    # Initialize editable equation fields through the local JavaScript decorator,
    # which adds relation shortcuts without modifying the pinned upstream script.
    rendered = rendered.replace("window.PLSymbolicInput(", "window.PLEquationInput(", 1)
    return rendered
