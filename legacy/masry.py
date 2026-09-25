
import sys
 
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass  
 
 
# ============================================================
# 0) الأخطاء
# ============================================================
class MasryError(Exception):
    """خطأ في لغة مصري — بيحمل رقم السطر."""
    def __init__(self, message, line=None):
        self.line = line
        if line is not None:
            super().__init__(f"❌ خطأ في السطر {line}: {message}")
        else:
            super().__init__(f"❌ خطأ: {message}")
 
 
# ============================================================
# 1) المحلّل اللفظي (Lexer) — بيحوّل النص لـ Tokens
# ============================================================
KEYWORDS = {
    'اطبع', 'خلي', 'لو', 'غير', 'كده', 'خلاص',
    'كرر', 'مرات', 'مرة', 'طالما', 'صح', 'غلط',
    'أكبر', 'أصغر', 'من', 'يساوي', 'مش', 'و', 'أو',
    'زائد', 'ناقص', 'في', 'على',
}
 
# تحويل الأرقام العربية (٠-٩) لأرقام إنجليزية عشان نحسبها
AR_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
 
# الحروف اللي بتقطع الكلمة
BREAKERS = set(' \t\r\n#"+-*/()<>=!')
 
 
def tokenize(source):
    tokens = []
    i, line, n = 0, 1, len(source)
 
    while i < n:
        c = source[i]
 
        # سطر جديد
        if c == '\n':
            tokens.append(('NEWLINE', '\n', line))
            line += 1
            i += 1
            continue
 
        # مسافات
        if c in ' \t\r':
            i += 1
            continue
 
        # تعليق لآخر السطر
        if c == '#':
            while i < n and source[i] != '\n':
                i += 1
            continue
 
        # نص بين علامتي تنصيص
        if c == '"':
            i += 1
            buf = ''
            while i < n and source[i] != '"':
                buf += source[i]
                i += 1
            if i >= n:
                raise MasryError('النص مقفلش بعلامة تنصيص "', line)
            i += 1  # نتخطى الـ " اللي بتقفل
            tokens.append(('STRING', buf, line))
            continue
 
        # علامات المقارنة بالرموز
        if c in '<>=!':
            two = source[i:i + 2]
            if two in ('>=', '<=', '==', '!='):
                tokens.append(('OP', two, line)); i += 2; continue
            if c == '=':
                tokens.append(('OP', '=', line)); i += 1; continue
            if c in '<>':
                tokens.append(('OP', c, line)); i += 1; continue
            raise MasryError("علامة '!' لوحدها مش مفهومة", line)
 
        # عمليات حسابية بالرموز والأقواس
        if c in '+-*/()':
            tokens.append(('OP', c, line)); i += 1; continue
 
        # رقم (إنجليزي أو عربي)
        if c.isdigit() or c in '٠١٢٣٤٥٦٧٨٩':
            start = i
            while i < n and (source[i].isdigit() or source[i] in '٠١٢٣٤٥٦٧٨٩' or source[i] == '.'):
                i += 1
            raw = source[start:i].translate(AR_DIGITS)
            value = float(raw) if '.' in raw else int(raw)
            tokens.append(('NUMBER', value, line))
            continue
 
        # كلمة (كلمة محجوزة أو اسم متغير)
        start = i
        while i < n and source[i] not in BREAKERS:
            i += 1
        word = source[start:i]
        kind = 'KW' if word in KEYWORDS else 'IDENT'
        tokens.append((kind, word, line))
 
    tokens.append(('NEWLINE', '\n', line))
    tokens.append(('EOF', None, line))
    return tokens
 
 
# ============================================================
# 2) المحلّل النحوي (Parser) — بيبني شجرة الأوامر (AST)
# ============================================================
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
 
    def peek(self):
        return self.tokens[self.pos]
 
    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok
 
    def at(self, kind, value=None):
        t = self.peek()
        return t[0] == kind and (value is None or t[1] == value)
 
    def eat(self, kind, value=None, msg=None):
        if not self.at(kind, value):
            got = self.peek()
            line = got[2]
            want = value if value else kind
            raise MasryError(msg or f"كنت متوقع '{want}' بس لقيت '{got[1]}'", line)
        return self.advance()
 
    def skip_newlines(self):
        while self.at('NEWLINE'):
            self.advance()
 
    def end_line(self):
        # لازم كل أمر يخلص بسطر جديد (أو نهاية الملف)
        if self.at('EOF'):
            return
        self.eat('NEWLINE', msg="محتاج تبدأ أمر جديد في سطر لوحده")
        self.skip_newlines()
 
    # ---- البرنامج ----
    def parse_program(self):
        self.skip_newlines()
        stmts = []
        while not self.at('EOF'):
            stmts.append(self.parse_statement())
            self.skip_newlines()
        return stmts
 
    def parse_block(self, terminators):
        """يقرأ أوامر لحد ما يوصل لكلمة إنهاء (زي خلاص / غير)."""
        self.skip_newlines()
        stmts = []
        while not self.at('EOF') and not any(self.at('KW', t) for t in terminators):
            stmts.append(self.parse_statement())
            self.skip_newlines()
        return stmts
 
    # ---- الأوامر ----
    def parse_statement(self):
        t = self.peek()
        if t[0] == 'KW':
            if t[1] == 'اطبع':   return self.parse_print()
            if t[1] == 'خلي':    return self.parse_assign()
            if t[1] == 'لو':     return self.parse_if()
            if t[1] == 'كرر':    return self.parse_repeat()
            if t[1] == 'طالما':  return self.parse_while()
        # إعادة تعيين متغير موجود: الاسم = قيمة
        if t[0] == 'IDENT':
            return self.parse_reassign()
        raise MasryError(f"مش عارف أعمل إيه بـ '{t[1]}'", t[2])
 
    def parse_print(self):
        self.eat('KW', 'اطبع')
        expr = self.parse_expr()
        self.end_line()
        return ('print', expr)
 
    def parse_assign(self):
        self.eat('KW', 'خلي')
        name = self.eat('IDENT', msg="بعد 'خلي' لازم يجي اسم المتغير")[1]
        self.eat('OP', '=', msg="محتاج علامة '=' بعد اسم المتغير")
        expr = self.parse_expr()
        self.end_line()
        return ('assign', name, expr)
 
    def parse_reassign(self):
        name = self.eat('IDENT')[1]
        self.eat('OP', '=', msg=f"'{name}' لازم يتبعه '=' لو عايز تغيّر قيمته")
        expr = self.parse_expr()
        self.end_line()
        return ('assign', name, expr)
 
    def parse_if(self):
        self.eat('KW', 'لو')
        cond = self.parse_expr()
        self.end_line()
        then_body = self.parse_block(['غير', 'خلاص'])
        else_body = None
        if self.at('KW', 'غير'):
            self.eat('KW', 'غير')
            self.eat('KW', 'كده', msg="بعد 'غير' لازم تكتب 'كده'")
            self.end_line()
            else_body = self.parse_block(['خلاص'])
        self.eat('KW', 'خلاص', msg="الشرط لازم يتقفل بكلمة 'خلاص'")
        self.end_line()
        return ('if', cond, then_body, else_body)
 
    def parse_repeat(self):
        self.eat('KW', 'كرر')
        count = self.parse_expr()
        if self.at('KW', 'مرات') or self.at('KW', 'مرة'):
            self.advance()
        else:
            raise MasryError("بعد عدد التكرار لازم تكتب 'مرات'", self.peek()[2])
        self.end_line()
        body = self.parse_block(['خلاص'])
        self.eat('KW', 'خلاص', msg="التكرار لازم يتقفل بكلمة 'خلاص'")
        self.end_line()
        return ('repeat', count, body)
 
    def parse_while(self):
        self.eat('KW', 'طالما')
        cond = self.parse_expr()
        self.end_line()
        body = self.parse_block(['خلاص'])
        self.eat('KW', 'خلاص', msg="'طالما' لازم تتقفل بكلمة 'خلاص'")
        self.end_line()
        return ('while', cond, body)
 
    # ---- التعبيرات (بترتيب الأولويات) ----
    def parse_expr(self):
        return self.parse_logic()
 
    def parse_logic(self):
        left = self.parse_comparison()
        while self.at('KW', 'و') or self.at('KW', 'أو'):
            op = self.advance()[1]
            right = self.parse_comparison()
            left = ('logic', op, left, right)
        return left
 
    def parse_comparison(self):
        left = self.parse_add()
        t = self.peek()
        op = None
        if t[0] == 'KW' and t[1] == 'أكبر':
            self.advance()
            if self.at('KW', 'أو'):
                self.advance(); self.eat('KW', 'يساوي'); op = '>='
            else:
                self.eat('KW', 'من', msg="بعد 'أكبر' اكتب 'من'"); op = '>'
        elif t[0] == 'KW' and t[1] == 'أصغر':
            self.advance()
            if self.at('KW', 'أو'):
                self.advance(); self.eat('KW', 'يساوي'); op = '<='
            else:
                self.eat('KW', 'من', msg="بعد 'أصغر' اكتب 'من'"); op = '<'
        elif t[0] == 'KW' and t[1] == 'يساوي':
            self.advance(); op = '=='
        elif t[0] == 'KW' and t[1] == 'مش':
            self.advance(); self.eat('KW', 'يساوي', msg="بعد 'مش' اكتب 'يساوي'"); op = '!='
        elif t[0] == 'OP' and t[1] in ('>', '<', '>=', '<=', '==', '!='):
            self.advance(); op = t[1]
 
        if op:
            right = self.parse_add()
            return ('compare', op, left, right)
        return left
 
    def parse_add(self):
        left = self.parse_mul()
        while (self.at('OP', '+') or self.at('OP', '-')
               or self.at('KW', 'زائد') or self.at('KW', 'ناقص')):
            raw = self.advance()[1]
            op = '+' if raw in ('+', 'زائد') else '-'
            right = self.parse_mul()
            left = ('binop', op, left, right)
        return left
 
    def parse_mul(self):
        left = self.parse_unary()
        while (self.at('OP', '*') or self.at('OP', '/')
               or self.at('KW', 'في') or self.at('KW', 'على')):
            raw = self.advance()[1]
            op = '*' if raw in ('*', 'في') else '/'
            right = self.parse_unary()
            left = ('binop', op, left, right)
        return left
 
    def parse_unary(self):
        if self.at('OP', '-') or self.at('KW', 'ناقص'):
            self.advance()
            return ('neg', self.parse_unary())
        return self.parse_primary()
 
    def parse_primary(self):
        t = self.peek()
        if t[0] == 'NUMBER':
            self.advance(); return ('num', t[1])
        if t[0] == 'STRING':
            self.advance(); return ('str', t[1])
        if t[0] == 'KW' and t[1] == 'صح':
            self.advance(); return ('bool', True)
        if t[0] == 'KW' and t[1] == 'غلط':
            self.advance(); return ('bool', False)
        if t[0] == 'IDENT':
            self.advance(); return ('var', t[1])
        if t[0] == 'OP' and t[1] == '(':
            self.advance()
            expr = self.parse_expr()
            self.eat('OP', ')', msg="قوس '(' مش متقفل")
            return expr
        raise MasryError(f"مش فاهم '{t[1]}' هنا", t[2])
 
 
# ============================================================
# 3) المنفّذ (Interpreter) — بيمشي على الشجرة وينفّذ
# ============================================================
def to_str(v):
    """يطبع القيمة بشكل مظبوط بالعربي."""
    if isinstance(v, bool):
        return 'صح' if v else 'غلط'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)
 
 
def is_true(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return len(v) > 0
    return v is not None
 
 
class Interpreter:
    def __init__(self):
        self.env = {}
 
    def run(self, stmts):
        for stmt in stmts:
            self.execute(stmt)
 
    def execute(self, stmt):
        kind = stmt[0]
 
        if kind == 'print':
            print(to_str(self.eval(stmt[1])))
 
        elif kind == 'assign':
            self.env[stmt[1]] = self.eval(stmt[2])
 
        elif kind == 'if':
            _, cond, then_body, else_body = stmt
            if is_true(self.eval(cond)):
                self.run(then_body)
            elif else_body is not None:
                self.run(else_body)
 
        elif kind == 'repeat':
            _, count_expr, body = stmt
            count = self.eval(count_expr)
            if not isinstance(count, (int, float)):
                raise MasryError("عدد التكرار لازم يكون رقم")
            for _ in range(int(count)):
                self.run(body)
 
        elif kind == 'while':
            _, cond, body = stmt
            guard = 0
            while is_true(self.eval(cond)):
                self.run(body)
                guard += 1
                if guard > 1_000_000:
                    raise MasryError("التكرار مالوش نهاية (طالما فضلت صح مليون مرة)")
 
        else:
            raise MasryError(f"أمر مش معروف: {kind}")
 
    def eval(self, node):
        kind = node[0]
 
        if kind == 'num':   return node[1]
        if kind == 'str':   return node[1]
        if kind == 'bool':  return node[1]
 
        if kind == 'var':
            name = node[1]
            if name not in self.env:
                raise MasryError(f"المتغير '{name}' مش معرّف. اكتب 'خلي {name} = ...' الأول")
            return self.env[name]
 
        if kind == 'neg':
            v = self.eval(node[1])
            if not isinstance(v, (int, float)):
                raise MasryError("علامة الناقص بتشتغل على الأرقام بس")
            return -v
 
        if kind == 'binop':
            _, op, l, r = node
            a, b = self.eval(l), self.eval(r)
            if op == '+':
                # لو أي طرف نص → نلزّق النصوص
                if isinstance(a, str) or isinstance(b, str):
                    return to_str(a) + to_str(b)
                return a + b
            if op == '-': return a - b
            if op == '*': return a * b
            if op == '/':
                if b == 0:
                    raise MasryError("مينفعش تقسم على صفر")
                return a / b
 
        if kind == 'compare':
            _, op, l, r = node
            a, b = self.eval(l), self.eval(r)
            if op == '>':  return a > b
            if op == '<':  return a < b
            if op == '>=': return a >= b
            if op == '<=': return a <= b
            if op == '==': return a == b
            if op == '!=': return a != b
 
        if kind == 'logic':
            _, op, l, r = node
            if op == 'و':
                return is_true(self.eval(l)) and is_true(self.eval(r))
            else:  # أو
                return is_true(self.eval(l)) or is_true(self.eval(r))
 
        raise MasryError(f"تعبير مش معروف: {kind}")
 
 
# ============================================================
# 4) التشغيل
# ============================================================
def run_source(source, interpreter):
    tokens = tokenize(source)
    stmts = Parser(tokens).parse_program()
    interpreter.run(stmts)
 
 
def run_file(path):
    try:
        with open(path, encoding='utf-8') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"❌ مش لاقي الملف: {path}")
        sys.exit(1)
    interpreter = Interpreter()
    try:
        run_source(source, interpreter)
    except MasryError as e:
        print(e)
        sys.exit(1)
 
 
def repl():
    print("=" * 50)
    print("  🇪🇬  أهلاً بيك في لغة (مصري)")
    print("  اكتب أوامرك بالعامية. للخروج اكتب: خروج")
    print("=" * 50)
    interpreter = Interpreter()
    buffer = []
    depth = 0
 
    while True:
        try:
            prompt = "...... " if buffer else "مصري> "
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("\nمع السلامة 👋")
            break
 
        if not buffer and line.strip() in ('خروج', 'exit'):
            print("مع السلامة 👋")
            break
 
        first = line.strip().split()[0] if line.strip() else ''
        if first in ('لو', 'كرر', 'طالما'):
            depth += 1
        elif first == 'خلاص':
            depth = max(0, depth - 1)
 
        buffer.append(line)
 
        if depth == 0:
            code = "\n".join(buffer)
            buffer = []
            if code.strip():
                try:
                    run_source(code, interpreter)
                except MasryError as e:
                    print(e)
                except Exception as e:
                    print(f"❌ حصل خطأ غير متوقع: {e}")
 
 
def main():
    if len(sys.argv) > 1:
        run_file(sys.argv[1])
    else:
        repl()
 
 
if __name__ == '__main__':
    main()
 
