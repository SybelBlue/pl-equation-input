import random

import sympy


def generate(data):
    x, y = sympy.symbols("x y")
    slope = random.choice([-4, -3, -2, 2, 3, 4])
    intercept = random.randint(-6, 6)
    answer = sympy.Eq(y, slope * x + intercept, evaluate=False)
    data["params"]["answer_latex"] = sympy.latex(answer)
    data["correct_answers"]["line"] = answer
