"""Safe calculator: own tokenizer + Pratt parser. No eval/exec, bounded numbers, recursion and input size."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

MAX_LEN = 300
MAX_DEPTH = 60
MAX_ABS = 1e300


class CalcError(ValueError):
    pass


class Pct(float):
    """A value produced by postfix % (so that `100 - 15%` = 85, like pocket calculators)."""


@dataclass
class Tok:
    kind: str  # num | op | lp | rp | name | comma | end
    value: str
    num: float = 0.0


FUNCS = {
    "sqrt": (1, math.sqrt), "cbrt": (1, lambda x: math.copysign(abs(x) ** (1 / 3), x)), "abs": (1, abs),
    "round": (None, lambda *a: round(a[0], int(a[1])) if len(a) > 1 else round(a[0])), "floor": (1, math.floor),
    "ceil": (1, math.ceil), "sin": (1, math.sin), "cos": (1, math.cos), "tan": (1, math.tan), "asin": (1, math.asin),
    "acos": (1, math.acos), "atan": (1, math.atan), "sinh": (1, math.sinh), "cosh": (1, math.cosh), "tanh": (1, math.tanh),
    "ln": (1, math.log), "log": (None, lambda *a: math.log(a[0], a[1]) if len(a) > 1 else math.log10(a[0])),
    "log10": (1, math.log10), "log2": (1, math.log2), "exp": (1, math.exp), "min": (None, min), "max": (None, max),
    "fact": (1, lambda x: _fact(x)), "deg": (1, math.degrees), "rad": (1, math.radians), "hyp": (2, math.hypot),
    "gcd": (2, lambda a, b: math.gcd(int(a), int(b))), "lcm": (2, lambda a, b: math.lcm(int(a), int(b))),
    "корень": (1, math.sqrt), "кв": (1, lambda x: x * x),
}
CONSTS = {"pi": math.pi, "π": math.pi, "e": math.e, "tau": math.tau, "пи": math.pi, "phi": (1 + 5 ** 0.5) / 2}
_NUM = re.compile(r"\d+(?:[.,]\d+)?(?:e[+-]?\d+)?|\.\d+", re.IGNORECASE)
_NAME = re.compile(r"[a-zа-яё_π][a-zа-яё_0-9]*", re.IGNORECASE)


def _fact(x: float) -> float:
    if x < 0 or x != int(x) or x > 170:
        raise CalcError("factorial: 0..170 integers only")
    return float(math.factorial(int(x)))


def tokenize(src: str) -> list[Tok]:
    s = src.replace("×", "*").replace("·", "*").replace("÷", "/").replace("−", "-").replace("–", "-").replace("**", "^")
    s = re.sub(r"\b(of|от|dan)\b", "*", s, flags=re.IGNORECASE)
    out: list[Tok] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
            continue
        m = _NUM.match(s, i)
        if m:
            text = m.group(0).replace(",", ".")
            out.append(Tok("num", text, float(text)))
            i = m.end()
            continue
        m = _NAME.match(s, i)
        if m:
            out.append(Tok("name", m.group(0).lower()))
            i = m.end()
            continue
        if c in "+-*/^%!":
            if c == "/" and s[i:i + 2] == "//":
                out.append(Tok("op", "//"))
                i += 2
                continue
            out.append(Tok("op", c))
        elif c in "([":
            out.append(Tok("lp", c))
        elif c in ")]":
            out.append(Tok("rp", c))
        elif c in ";":
            out.append(Tok("comma", c))
        else:
            raise CalcError(f"unexpected symbol: {c}")
        i += 1
    out.append(Tok("end", ""))
    return out


class Parser:
    BIN = {"+": 10, "-": 10, "*": 20, "/": 20, "//": 20, "%": 20, "^": 30}

    def __init__(self, tokens: list[Tok]) -> None:
        self.t = tokens
        self.i = 0
        self.depth = 0

    def peek(self) -> Tok:
        return self.t[self.i]

    def next(self) -> Tok:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def parse(self) -> float:
        v = self.expr(0)
        if self.peek().kind != "end":
            raise CalcError("unexpected token: " + self.peek().value)
        return v

    def expr(self, min_bp: int) -> float:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise CalcError("expression too deep")
        left = self.prefix()
        while True:
            tok = self.peek()
            if tok.kind == "op" and tok.value == "!":
                self.next()
                left = _fact(left)
                continue
            if tok.kind == "op" and tok.value == "%":
                nxt = self.t[self.i + 1]
                if nxt.kind in ("end", "rp", "comma") or (nxt.kind == "op" and nxt.value in "+-*/"):
                    self.next()
                    left = Pct(left / 100.0)
                    continue
            if tok.kind != "op" or tok.value not in self.BIN:
                break
            bp = self.BIN[tok.value]
            if bp < min_bp:
                break
            self.next()
            right = self.expr(bp if tok.value == "^" else bp + 1)
            left = self.apply(tok.value, left, right)
        self.depth -= 1
        return left

    def prefix(self) -> float:
        tok = self.next()
        if tok.kind == "num":
            v = tok.num
        elif tok.kind == "op" and tok.value in "+-":
            v = self.expr(25)
            v = -v if tok.value == "-" else v
            return v
        elif tok.kind == "lp":
            v = self.expr(0)
            if self.next().kind != "rp":
                raise CalcError("missing )")
        elif tok.kind == "name":
            if tok.value in CONSTS:
                v = CONSTS[tok.value]
            elif tok.value in FUNCS:
                arity, fn = FUNCS[tok.value]
                if self.next().kind != "lp":
                    raise CalcError(f"{tok.value}: expected (")
                args = [self.expr(0)]
                while self.peek().kind == "comma":
                    self.next()
                    args.append(self.expr(0))
                if self.next().kind != "rp":
                    raise CalcError("missing )")
                if arity is not None and len(args) != arity:
                    raise CalcError(f"{tok.value}: expects {arity} argument(s)")
                try:
                    v = float(fn(*args))
                except (ValueError, OverflowError, ZeroDivisionError) as e:
                    raise CalcError(f"{tok.value}: {e}") from None
            else:
                raise CalcError(f"unknown name: {tok.value}")
        else:
            raise CalcError("unexpected token: " + (tok.value or "end"))
        # implicit multiplication: 2(3), 2pi, (1+2)(3)
        nxt = self.peek()
        if nxt.kind in ("lp", "name") or (nxt.kind == "num" and tok.kind in ("rp", "lp")):
            v = v * self.prefix()
        return self.check(v)

    @staticmethod
    def check(v: float) -> float:
        if isinstance(v, float) and (math.isnan(v) or abs(v) > MAX_ABS):
            raise CalcError("result out of range")
        return v

    def apply(self, op: str, a: float, b: float) -> float:
        try:
            if op == "+":
                r = a + a * b if isinstance(b, Pct) else a + b
            elif op == "-":
                r = a - a * b if isinstance(b, Pct) else a - b
            elif op == "*":
                r = a * b
            elif op == "/":
                r = a / b
            elif op == "//":
                r = float(math.floor(a / b))
            elif op == "%":
                r = math.fmod(a, b)
            else:
                if abs(b) > 10000 or (abs(a) > 1 and b * math.log10(abs(a)) > 300):
                    raise CalcError("power too large")
                r = a ** b
                if isinstance(r, complex):
                    raise CalcError("complex result")
        except ZeroDivisionError:
            raise CalcError("division by zero") from None
        except OverflowError:
            raise CalcError("result out of range") from None
        return self.check(float(r))


def evaluate(expr: str) -> float:
    expr = (expr or "").strip().rstrip("=").strip()
    if not expr:
        raise CalcError("empty expression")
    if len(expr) > MAX_LEN:
        raise CalcError("expression too long")
    # function argument separator: allow ',' between args only inside f( ... ) when followed by space or not digit-decimal
    expr = re.sub(r",\s+", ";", expr)
    return Parser(tokenize(expr)).parse()


def fmt_number(v: float) -> str:
    if v == int(v) and abs(v) < 1e16:
        return f"{int(v):,}".replace(",", " ")
    if abs(v) >= 1e12 or (abs(v) < 1e-6 and v != 0):
        return f"{v:.10g}"
    return f"{v:.10f}".rstrip("0").rstrip(".")
