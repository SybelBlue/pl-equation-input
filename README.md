# `pl-equation-input`

Enter and grade one symbolic equation or inequality using a standard symbolic-input field.

```html
<pl-equation-input
  answers-name="line"
  correct-answer="y = 2*x + 1"
  formula-editor="true"
  variables="x, y"
></pl-equation-input>
```

The correct answer may instead be supplied by `server.py`:

```python
x, y = sympy.symbols("x y")
data["correct_answers"]["line"] = sympy.Eq(y, 2 * x + 1, evaluate=False)
```

## Attributes

| Attribute                  | Default      | Description                                                                                                  |
| -------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------ |
| `answers-name`             | —            | Required unique answer name.                                                                                 |
| `allow-inequalities`       | `false`      | Also accept ASCII, Unicode, and LaTeX inequality signs such as `<=`, `≤`, and `\le`.                         |
| `correct-answer`           | —            | Relation containing exactly one allowed comparison sign. May be omitted when `server.py` supplies an answer. |
| `display`                  | `inline`     | Display the underlying symbolic input as `inline` or `block`.                                                |
| `formula-editor`           | `false`      | Use the visual MathLive editor.                                                                              |
| `grading-method`           | `equivalent` | Grade using `exact`, `equivalent`, `component`, or `none`.                                                   |
| `label`                    | —            | Content displayed before the field.                                                                          |
| `lhs-relative-weight`      | `1`          | Nonnegative LHS weight in component grading.                                                                 |
| `operator-relative-weight` | `1`          | Nonnegative comparison-operator weight in component grading.                                                 |
| `placeholder`              | `equation`   | Placeholder text displayed when the input is empty.                                                          |
| `rhs-relative-weight`      | `1`          | Nonnegative RHS weight in component grading.                                                                 |
| `size`                     | `35`         | Text-field size.                                                                                             |
| `variables`                | —            | Comma-delimited variables allowed on either side.                                                            |
| `weight`                   | `1`          | Weight in the question score.                                                                                |

At least one component relative weight must be positive. The three relative-weight attributes have no effect outside component grading.

The student enters exactly one comparison sign. The element splits and parses its two sides, then stores the complete relation as one JSON-safe answer. Its self-contained input renderer retains the standard `pl-symbolic-input` formula editor and help behavior without creating an auxiliary answer name. The posted text, normalized relation, format errors, and score all use `answers-name`. Chained relations and set-valued input are not supported.

## Grading methods

### Equivalent

`equivalent` is the default. It awards full credit when the submitted and correct relations have the same real solution set. All free symbols in either relation are treated as coordinates, so this also supports equations describing curves in two variables.

For the correct answer `x + 1 = y`, all of these are equivalent:

```text
x + 1 = y
y = x + 1
x = y - 1
2*x + 2 = 2*y
```

Different relation types may be equivalent. For example, `x = 0` and `x^2 <= 0` have the same real solution set.

The grader first simplifies the logical equivalence, uses exact real solution sets for univariate relations, and then applies conservative algebraic proofs for multivariable relations. It never infers equivalence from numerical samples. Because general multivariable solution-set equality is not decidable by SymPy, a relation receives no credit when equivalence cannot be proven; use `exact` when the expected form matters or the desired equivalence is outside these checks.

### Exact

`exact` compares the canonical expressions produced by the symbolic parser. It accepts a side swap, simultaneous negation of both sides, or both, while transforming an inequality sign as required. It does not permit arbitrary scaling or moving terms between sides.

For `x + 1 = y`, these receive full credit:

```text
x + 1 = y    # original
y = x + 1    # swapped left/right
-x - 1 = -y  # both negated
-y = -x - 1  # negated and swapped
```

However, the equivalent forms `x = y - 1` and `2*x + 2 = 2*y` do not receive credit in exact mode.

For an inequality such as `x < y`, the exact transformations are `y > x`, `-x > -y`, and `-y < -x`. Changing `<` to `<=` is not exact.

### Component

`component` grades the positional LHS, operator, and RHS separately using the same canonical structural comparison as exact mode. It does not swap or negate the relation. The score is

```text
sum(weights of matching components) / sum(all component weights).
```

For example, this gives the LHS twice the weight of the RHS and ignores the operator:

```html
<pl-equation-input
  answers-name="relation"
  correct-answer="x + 1 = y"
  grading-method="component"
  lhs-relative-weight="2"
  operator-relative-weight="0"
  rhs-relative-weight="1"
  variables="x, y"
></pl-equation-input>
```

The submission `x + 1 < x` earns `2/3`: only its LHS matches. The submission panel shows one aggregate score badge because the relation is entered in one field.

### None

`none` parses and records the response without creating a score. A correct answer is optional; when supplied, it is still displayed in the correct-answer panel.

```html
<pl-equation-input
  answers-name="model"
  correct-answer="y = 2*x + 1"
  grading-method="none"
  variables="x, y"
></pl-equation-input>
```

Omitting a correct answer also leaves the response ungraded under any grading method.

## Inequalities

Enable inequalities explicitly:

```html
<pl-equation-input
  answers-name="bound"
  allow-inequalities="true"
  correct-answer="x &lt; 4"
  variables="x"
></pl-equation-input>
```

Accepted spellings include `<`, `<=`, `>`, `>=`, `≤`, `≥`, `\lt`, `\le`, `\leq`, `\gt`, `\ge`, and `\geq`.
In the formula editor, typing `<=` or `>=` displays the corresponding single relation glyph. The math keyboard provides dedicated `=`, `<`, and `>` keys; Shift changes `<` and `>` to `≤` and `≥`.
