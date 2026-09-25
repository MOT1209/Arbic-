# Phase 1 — التحليل المعماري / Architecture Analysis

> مستند تخطيطي لتحويل مشروع **Masry (مصري)** إلى **AlArabiya (العربية)**.
> يُقرأ هذا المستند قبل أي تعديل كود، ويُحدَّث عند تغيّر القرارات المعمارية.

---

## 1. Current Architecture (الوضع الحالي)

المستودع قبل إعادة الهندسة كان يتكوّن من ثلاثة ملفات فقط:

```text
masry/
├── masry.py      # كل شيء: الأخطاء + Lexer + Parser + Interpreter + CLI + REPL (526 سطر)
├── README.md
└── test.masr     # مثال واحد
```

### 1.1 المراحل Execution القديمة

```text
Source (نص)
  │
  ▼
tokenize(source)                 # دالة حرة، ترجع list[tuple]
  │   tuple = (TYPE, value, line)
  ▼
Parser(tokens).parse_program()   # recursive descent، يرجع list[tuple]
  │   AST = tuples مثل ('binop', '+', left, right)
  ▼
Interpreter().run(stmts)         # يمشي على الـ tuples وينفّذ
```

### 1.2 المكوّنات بالتفصيل

| المكوّن | الموقع | الشكل |
|---|---|---|
| Error type | `MasryError(Exception)` | رسالة نصية + رقم سطر فقط |
| Lexer | `tokenize()` دالة حرة | tuples `(kind, value, line)`؛ `KEYWORDS` set؛ `BREAKERS` set تقطع الكلمات |
| Parser | `class Parser` | recursive descent ثابت لكل مستوى أولوية (`parse_logic → parse_comparison → parse_add → parse_mul → parse_unary → parse_primary`) |
| AST | tuples معرّبة | `('print', expr)`، `('assign', name, expr)`، `('if', cond, then, else)` … إلخ |
| Interpreter | `class Interpreter` | `env: dict` مسطّح عالمي واحد؛ `eval/execute` switch على `node[0]` |
| CLI | `main()` | `python masry.py file` أو REPL |
| REPL | `repl()` | buffering بعدّاد عمق يدوي (`لو/كرر/طالما` +1، `خلاص` −1) |

### 1.3 قواعد اللغة المُوثّقة (السلوك المحفوظ)

- **أوامر:** `اطبع`، `خلي X = E`، `X = E` (إعادة تعيين)، `لو/غير كده/خلاص`، `كرر N مرات/مرة/خلاص`، `طالما/خلاص`.
- **أولويات التعبيرات** (من الأقل للأعلى): `و/أو` ← مقارنات (`أكبر من`، `أصغر من`، `أكبر أو يساوي`، `أصغر أو يساوي`، `يساوي`، `مش يساوي`، ورموز `> < >= <= == !=`) ← `+ - زائد ناقص` ← `* / في على` ← unary `- ناقص` ← primary (رقم، نص، `صح/غلط`، متغير، `(…)`).
- **نص:** توسية `+` بين نص ورقم تلزّق (`"السن: " + 25` → `السن: 25`).
- **أرقام:** عربية `٠-٩` وإنجليزية؛ صحيح أو عشري.
- **تعليقات:** `#` حتى نهاية السطر.
- **ال新格局:** علامات نهاية السطر `NEWLINE` مُهمّة (كل أمر في سطر)، لكن **المسافة البادئة غير حساسة** (الكتل تنتهي بكلمة `خلاص`).
- **semantic قديم:** الإسناد لغير معرّف ينشئ المتغير صامتًا؛ `while` له حارس 1,000,000 تكرار؛ القسمة على صفر خطأ؛ `صح/غلط` تطبع كما هما.

---

## 2. Problems (المشاكل)

### P1 — ملف واحد يخلط كل الطبقات
`masry.py` يجمع lexer وparser وAST وinterpreter وCLI وREPL. لا يمكن اختبار طبقة بدون الأخرى، ولا إعادة استخدام أي جزء (LSP، bytecode، ترجمة أخطاء مستقلا).

### P2 — AST على شكل tuples معرّبة
- لا يوجد тип للعقد، فقط `node[0]` كنص سحري؛ أي typo في `kind` يفشل وقت التشغيل فقط.
- **لا مواقع مصدرية** في العقد إطلاقًا (السطر موجود في الـ tokens فقط ويضيع عند البناء).
- أي إضافة (دوال، arrays) تكسر كل `if kind == ...` في الطرفين parser وinterpreter.

### P3 — نظام أخطاء عشوائي
- `MasryError` يحمل سطرًا فقط: **لا column، لا offset، لا snippet، لا كود خطأ، لا شدة (severity).**
- رسائل الخطأ مبعثرة كـ f-strings داخل lexer/parser/interpreter.
- لا تمييز Error/Warning/Info/Hint، ولا إمكانية تجميع أخطاء متعددة (يفشل أول خطأ فقط).

### P4 — Lexer ضعيف ومقيد
- **لا column/offset** — `(kind, value, line)` فقط.
- تقسيم الكلمات بـ `BREAKERS = set(' \t\r\n#"+-*/()<>=!')` = قائمة مغلقة تخلط بين whitespace وcomment وstring وoperators؛ إضافة أي فاصل جديد (مثل `{ } , : .`) تعني تعديل القائمة والنتيجة الجانبية غير المتوقعة (مثل: `.` تُدخل داخل الـ identifiers!).
- لا escape sequences داخل النصوص إطلاقًا (`"a\"b"` مستحيل).
- الفاصلة العشرية العربية `٫` غير مدعومة (رغم أن README يدّعي دعم الأرقام العربية).
- أرقام مثل `1..2` أو `1.2.3` تنتج `ValueError` من `float()` **غير مُعالَج** → crash بـ traceback بايثون بدل خطأ لغوي.
- `!` مفردة ترمي خطأ من داخل الـ lexer مباشرة (لا diagnostics).
- الكلمات المحجوزة set واحدة مسطّحة؛ لا تسلسل هرمي ولا سهولة إضافة منظّمة.

### P5 — Parser غير مستقل وقابلية توسيع معدومة
- recursive descent مكتوب يدويًا لكل مستوى أولوية؛ إضافة calls/arrays/member-access/generics تعني إعادة كتابة `parse_primary` وinsert مستويات جديدة في المنتصف.
- الأخطاء `raise MasryError` مباشرة من داخل العميق — **لا error recovery**، أي خطأ يوقف التحليل (لا `check` يعطيك كل الأخطاء).
- الـ parser يعرف أنه «يجب أن ينتهي السطر بـ NEWLINE» موزّعًا في عشر أماكن (`end_line`).

### P6 — Runtime مرتبط بالـ frontend
`run_source()` تخلط: tokenize → parse → run في دالة واحدة. لا يمكن استدعاء «تحليل فقط» (وهو بالضبط ما يحتاجه `check` و LSP المستقبلي).

### P7 — Scope مسطّح بلا تصميم مستقبلي
`env: dict` واحد — لا parent chain، لا Way لبناء Function Scope / Block Scope / Module Scope لاحقًا بدون تغيير الـ interpreter كله.

### P8 — لا Tests إطلاقًا
صفر اختبارات. أي إعادة هندسة = كسر صامت لسلوك موجود.

### P9 — لا Packaging ولا أدوات
لا `pyproject.toml`، لا entry point، لا lint/type-check، لا توثيق هندسي، الامتداد `.masr`، الاسم `Masry` مطبوع في كل مكان.

---

## 3. Technical Debt

| # | الدين | الأثر | خطة السداد |
|---|---|---|---|
| TD1 | AST tuples | منع أي ميزة جديدة | استبداله بـ dataclass hierarchy كامل |
| TD2 | أخطاء نصية بلا مواقع | صعوبة debugging وLSP | Diagnostics system مركزي بـ Span |
| TD3 | lexer بـ BREAKERS | إضافة tokens = كسر متوقع | charset-based scanning منفصل لكل نوع |
| TD4 | parser غير قابل للتوسيع | كل ميزة = rewrite | Pratt parser + binding powers |
| TD5 | لا tests | كسر غير مكتشف | pytest لكل طبقة + regression بالمقارنة مع legacy |
| TD6 | frontend/runner مخلوطان | منع check/LSP | `frontend.py` مستقل يرجع `FrontendResult` |
| TD7 | env مسطّح | منع الدوال | `Environment(parent=)` chain |
| TD8 | سلوك غير موثّق (implicit declaration، حارس الـ while) | قرارات موروثة | توثيقه صراحة في هذا المستند وفي tests |

---

## 4. Proposed Architecture (البنية المقترحة)

### 4.1 مخطط الطبقات

```text
                    ┌──────────────────────────────┐
   ملف ‎main.arb ──►│  cli/  (argparse, exit codes)│
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │ compiler/frontend.py          │
                    │  compile_source(src, file)    │──► FrontendResult
                    └──┬──────────┬─────────────┬───┘      (program + diagnostics)
                       │          │             │
        ┌──────────────▼──┐  ┌────▼─────────┐  ┌▼──────────────────┐
        │ compiler/lexer/ │  │compiler/parser│  │ compiler/ast/      │
        │  positions.py   │  │ precedence.py │  │  nodes.py          │
        │  tokens.py      │  │ parser.py     │  │  visitor.py        │
        │  lexer.py       │  └────┬─────────┘  └───────────────────┘
        └────────┬────────┘       │
                 │ Tokens         │ AST (dataclasses + Span)
        ┌────────▼────────────────▼────────────────────┐
        │ compiler/diagnostics/                        │
        │  source.py (SourceFile, line indexing)       │
        │  errors.py (codes, exception bridge)         │
        │  diagnostics.py (Diagnostic, Bag, renderer)  │
        └──────────────────────────────────────────────┘
                                   │ AST فقط (لا تنفيذ في الـ frontend)
                    ┌──────────────▼───────────────┐
                    │ runtime/interpreter/          │
                    │  environment.py (scope chain) │
                    │  interpreter.py (visitor)     │
                    └──────────────┬───────────────┘
                                   │ قيم + أخطاء تشغيل كـ Diagnostics
```

### 4.2 قواعد الفصل (Invariants)

1. **الـ lexer لا يعرف parser أو runtime** — يرجع `list[Token]` فقط.
2. **الـ parser لا ينفّذ ولا يعرف runtime** — يرجع `Program` أو diagnostics.
3. **الـ interpreter يقبل AST فقط** — لا يرى tokens ولا نص مصدر.
4. **أي خطأ في أي طبقة = `Diagnostic`** لا استثناء نصي/ traceback.
5. **لا global mutable state** — كل حالة داخل كائنات (`Lexer`, `Parser`, `Interpreter`, `Environment`).

### 4.3 بنية الملفات النهائية

```text
al-arabiya/                        # الاسم الجديد للمستودع
├── al_arabiya/                    # حزمة بايثون (لتفادي تعارض أسماء الحزم generic)
│   ├── __init__.py                # __version__، اسم اللغة
│   ├── __main__.py                # python -m al_arabiya
│   ├── compiler/
│   │   ├── lexer/    positions.py tokens.py lexer.py
│   │   ├── parser/   precedence.py parser.py
│   │   ├── ast/      nodes.py visitor.py
│   │   ├── diagnostics/  source.py errors.py diagnostics.py
│   │   └── frontend.py
│   ├── runtime/
│   │   └── interpreter/  environment.py interpreter.py
│   └── cli/    main.py repl.py
├── tests/
│   ├── lexer/ parser/ ast/ diagnostics/ interpreter/ cli/
│   ├── integration/ regression/
│   └── conftest.py
├── examples/                     # ‎*.arb
├── legacy/                       # masry.py الأصلي (للمقارنة أثناء الـ regression فقط)
├── docs/  language/ architecture/ development/
├── tools/  check.py               # pytest + ruff + mypy في أمر واحد
├── pyproject.toml  README.md  LICENSE  .gitignore
```

**ملاحظة عن الانحراف عن الهيكل المقترح في المهمة:** الدمج داخل حزمة `al_arabiya/` بدل جعل `compiler/` و`runtime/` و`cli/` top-level — سبب تقني: أسماء حزم عامة مثل `compiler` تتعارض مع حزم أخرى عند `pip install`، والحزمة الموحّدة تمكّن entry point `arabic = al_arabiya.cli.main:main`. باقي التقسيم مطابق للمطلوب.

### 4.4 تصميم المفاتيح (القرارات الجوهرية)

**Positions**
```python
Position(offset: int, line: int, column: int)   # line/column = 1-based
Span(start: Position, end: Position)            # half-open [start, end)
```
كل `Token` وكل `ASTNode` يحمل `Span`. العمود يُحسب بالـ code points (Unicode-safe).

**Token model**
- `TokenType` = `enum.Enum`؛ **كل كلمة محجوزة عضو مستقل** (`KW_PRINT = "اطبع"`) → إضافة keyword = إضافة سطر واحد + سطر في جدول lexer، ومطابقة الـ parser type-safe.
- نوع لكل delimiter مطلوب في المواصفات الآن (`{ } [ ] , : .`) **رغم عدم استخدامها في grammar اليوم** — حتى يصبح إضافة Arrays/Objects لاحقًا lexer-only change.
- `Token` dataclass: `type, value (int|float|str|None), span, raw` (النص الخام للأرقام — أساس لإضافة أنواع رقمية لاحقًا: BigInteger، rationals).
- تطبيع الأرقام: `٠-٩` و`۰-۹` → ASCII، `٫` (U+066B) → `.`، وتجاهل `٬` (U+066C) كفاصل آلاف.

**Diagnostics**
```python
Severity = ERROR | WARNING | INFO | HINT
Diagnostic(code, severity, message, span, suggestion=None, notes=())
DiagnosticBag.add(...) / .errors / .has_errors / .sorted
render(diagnostic, source) -> str     # عربي RTL: كود + موقع + snippet + carets + اقتراح
```
تقسيمة الأكواد:

| المدى | النطاق |
|---|---|
| `E1xxx` | lexical (حرف غير متوقع، نص غير مغلق، escape خاطئ، رقم فاسد) |
| `E2xxx` | syntax (token ناقص، `خلاص` مفقودة، أمر غير معروف) |
| `W3xxx` | تحذيرات semantic (إسناد صامت لمتغير غير معلن) |
| `E4xxx` | runtime (متغير غير معرّف، قسمة على صفر، نوع خاطئ) |

**Parser — Precedence Climbing (Pratt)**
- `parse_expression(min_bp)` مع binding powers: `أو`=1، `و`=2، مقارنة=3، `+ -`=4، `* /`=5، prefix `-`=6.
- الفرق عن recursive descent المكتوب يدويًا: إضافة call/member/array/generics = إضافة parselet واحد في جدول، بلا تعديل الهيكل.
- **Panic-mode recovery:** عند خطأ statement-level يتم التخلص حتى `NEWLINE` التالية واستئناف التحليل → `arabic check` يعرض كل الأخطاء دفعة واحدة.

**AST**
- `@dataclass(slots=True)` متداخلة: `ASTNode` ← `Statement`/`Expression` ← أنواع فرعية. كل عقدة بـ `span`.
- `ASTVisitor` في `visitor.py` (زيارت مزدوجة: `visit_x` ينفّذ ثم `generic_visit`) — الـ interpreter يورث منه؛ مستقبلًا LSP/bytecode ترجمة تورث منه هي أيضًا.
- العمليات تُوحَّد رمزيًا عند البناء: `زائد→+`، `أكبر من→>`، `مش يساوي→!=` …؛ `و/أو` تبقى عربية (تمييزها linguistic).

**Environment**
```python
Environment(parent: Environment | None = None)
  define(name, value)      # يحدّد في هذا الـ scope
  get(name)                # يبحث في هذا scope ثم parent… (Chain lookup)
  assign(name, value)      # يحدّد على المتغيّر القائم في أقرب scope، وإلا E4001
```
**قرار موثّق (مهم):** في Phase 1 الـ interpreter يشغّل كل الكتل على scope واحد (سلوك Masry الأصلي: المتغيرات تعيش خارج الكتل، وهذا شرط حفاظ الـ regression). الشجرة الهرمية **مصمّمة ومختبَرة الآن**، وتُفعَّل للكتل عند مرحلة Functions — لا كسر سلوك.

### 4.5 CLI / REPL

```bash
arabic run main.arb      # compile + interpret
arabic check main.arb    # compile فقط → كل الـ diagnostics، بدون تنفيذ
arabic repl              # واجهة مباشرة تفاعلية
arabic version           # arabic 0.1.0 (AlArabiya / العربية)
arabic help
```
- أكواد الخروج: `0` نجاح، `1` أخطاء ترجمة (check/run)، `2` خطأ تشغيل، `3` خطأ استخدام/داخلي.
- REPL: بانر `العربية REPL`، prompt `>>> `، **نفس تقنية multi-line buffer** (تُحسب أقواس/بدايات كتل عبر الـ tokens نفسها بدل عدّ الكلمة الأولى يدويًا)، بيئة `Environment` ثابتة بين الإدخالات، أوامر خروج `خروج`/`exit`.
- دعم الترميز: `sys.stdout.reconfigure(encoding="utf-8")` يبقى في طبقة CLI فقط (كما في legacy) — لا في المكوّنات.

---

## 5. Migration Strategy (استراتيجية التحويل)

التحويل **in-place داخل نفس المستودع** (حتى يبقى git history كاملًا؛ التغييرات كـ `git mv` + تعديلات، لا re-init).

### الخطوات (تسلسل تنفيذي):

1. **Baseline** — تثبيت المخرجات الذهبية للـ legacy (`legacy/masry.py test.masr`) في `tests/regression/`.
2. **التخطيط** — هذا المستند (`docs/architecture/phase-1-analysis.md`). لا كود قبله.
3. **الأساس** — `pyproject.toml` + هيكل الحزمة + `diagnostics/` (لأن كل طبقة تعتمده).
4. **Frontend** — `positions/tokens/lexer` ← `ast/` ← `precedence/parser` ← `frontend.py`، مع اختبارات كل واحد قبل التالي.
5. **Runtime** — `environment` ثم `interpreter` فوق الـ AST الجديدة.
6. **CLI + REPL** — فوق `frontend` + `runtime`.
7. **Regression** — مقارنة مخرجات programs `.arb` بالمخرجات الذهبية (+ مقارنة مباشرة مع legacy script اختياريًا عبر subprocess).
8. **Rebrand + Docs** — README، أمثلة `.arb`، docs/language، docs/development.
9. **Quality gate** — `ruff check` + `mypy` + `pytest` كلها خضراء عبر `tools/check.py`.
10. **Retire legacy** — `legacy/masry.py` يبقى مرجعيًا فقط **خارج** مسار التشغيل؛ المشروع لا يستدعيه في أي مسار تنفيذ عادي.

### ما يُعاد استخدامه (Reuse)
- **السلوك اللغوي بالكامل** (الكلمات المفتاحية، الأولويات، semantics الطباعة/التلزيق/الحارس) — يُنقل كـ specs واختبارات.
- **القرارات الذكية في legacy:** حارس الـ `while` (1M)، `to_str` العربي (`صح/غلط`، الصحيح العشري)، قاموس الكلمات، منطق `is_true`.
- **`legacy/masry.py`** كمرجع مقارنة دائم.

### ما يُعاد كتابته (Rewrite)
- Lexer (positions، tokens enum، charset-based)، Parser (Pratt + recovery)، AST (dataclasses + visitor)، Diagnostics (جديد كليًا)، Interpreter (visitor + environment)، CLI/REPL، Docs، Tests.

### ما يُحذف/يُستبدل
- tuples AST، `MasryError` كوسيلة إبلاغ أساسية، `BREAKERS`، `run_source` المختلطة، امتداد `.masr` كامتداد أساسي (يظل legacy/compat في tests).

---

## 6. Risks (المخاطر)

| # | الخطر | احتمال/أثر | التخفيف |
|---|---|---|---|
| R1 | كسر سلوك غير مقصود أثناء الـ rewrite | واطي/عالٍ | مخرجات ذهبية + مقارنة مباشرة مع legacy script في regression tests |
| R2 | تغيّر دلالات الـ scopes يكسر برامج حالية | عالي إن وقع | مُقرَّر: scope واحد في Phase 1 (§4.4) ومختبَر صراحة |
| R3 | تقديم/تحليل RTL (المصادر عربية برمجيًا UTF-8 لكن العمود قد يُحسب خطأ) | واطي/متوسط | حساب positions على code points + اختبارات وحدات على عمود محدّد؛ الـ renderer يعرض السطر خامًا مع carets بالإزاحة الحرفية |
| R4 | اصطدام `check` بالأخطاء المتعددة يُنتج دفعات مكررة | متوسط | `DiagnosticBag` بمنطقة حجز (dedupe حسب code+span) + حد أقصى للأخطاء |
| R5 | إعادة استخدام أسماء حزم generic | عالي إن وقع | حزمة `al_arabiya` الموحّدة (§4.3) |
| R6 | فقدان git history | واطي | `git mv` فقط، لا re-init، لا force-push |
| R7 | REPL multi-line heuristic يكسر مع أقواس متعادلة | واطي | Buffering يعتمد على أقواس/كلمات إغلاق من الـ tokens الفعلية |
| R8 | توسعة الـ lexer (delimiters جديدة) تكسر identifiers قديمة | واطي | charset معلن: identifiers = Unicode letters + `_` + digits بعد الأول؛ اختبارات تغطي حروفًا عربية/إنجليزية/محايدة |

---

## 7. Testing Strategy (استراتيجية الاختبار)

**الأداة:** `pytest` (وحدات + تكامل). معيار النجاح: `pytest` + `ruff` + `mypy` أخضر.

### 7.1 خريطة الاختبارات

```text
tests/
├── conftest.py              # fixtures: lex(), parse(), run() مساعدة
├── lexer/
│   ├── test_identifiers.py  # عربي/إنجليزي/مختلط/underscore/معرّفات كـ keywords
│   ├── test_numbers.py      # 123، ١٢٣، 12.5، ١٢٫٥، ۰-۹، صحة raw/value، أخطاء 1..2
│   ├── test_strings.py      # تنصيص، escapes (\\ \" \n \t \u{})، خطأ عدم الإغلاق
│   ├── test_operators.py    # كل الرموز + keywords المتعددة الكلمات (لمستوي المفردات)
│   ├── test_delimiters.py   # ( ) [ ] { } , : .
│   ├── test_keywords.py     # كل keyword → TokenType الصحيح؛ IDENT للكلمات العادية
│   ├── test_positions.py    # line/column/offset/length على مصادر عربية حقيقية
│   ├── test_comments_ws.py  # # تعليق، مسافات، newlines، EOF
│   └── test_errors.py       # حرف غير متوقع، ! مفردة → E1xxx بموقع صحيح
├── parser/
│   ├── test_statements.py   # طبع/خلي/إعادة تعيين/if/repeat/while
│   ├── test_expressions.py  # أولويات كاملة (منطق/مقارنة/جمع/ضرب/unary/أقواس)
│   ├── test_precedence.py   # جداول حالات: 2+3*4، و/أو، مقارنات رمزية vs عربية
│   └── test_syntax_errors.py# خلاص ناقصة، = ناقصة، شرط فارغ… → E2xxx + recovery
├── ast/
│   ├── test_nodes.py        # شكل الشجرة، types، dataclass صفة
│   └── test_locations.py    # span لكل عقدة من program إلى literal
├── diagnostics/
│   ├── test_diagnostic.py   # severity/codes/bag/dedupe
│   ├── test_render.py       # كود+موقع+snippet+carets+اقتراح، ترميز عربي
│   └── test_source.py       # line indexing، عمود بعد نص عربي، ملف غير موجود
├── interpreter/
│   ├── test_statements.py   # print/declare/assign/if/repeat/while
│   ├── test_expressions.py  # حساب، تلزيق نصوص، مقارنات، منطق، صح/غلط
│   ├── test_environment.py  # define/get/assign + سلسلة parent scopes
│   └── test_runtime_errors.py  # E4xxx: متغير مجهول، قسمة صفر، نوع، حارس while
├── cli/
│   ├── test_cli.py          # run/check/version/help/repl (subprocess أو main(argv))
│   └── exit codes + رسائل stderr/stdout
├── integration/
│   └── test_programs.py     # programs كاملة: مصدر → مخرجات نصية متوقعة
└── regression/
    ├── programs/*.arb       # كل أمثلة Masry المحوّلة (test.masr وغيره)
    ├── expected/*.txt       # المخرجات الذهبية من legacy
    └── test_regression.py   # مقارنة صريحة + تشغيل legacy/masry.py كمرجع (subprocess)
```

### 7.2 حالات الاختبار الإلزامية (من مواصفات Phase 1)

- **Lexer:** معرّفات عربية/إنجليزية، أرقام عربية/إنجليزية/عشية، نصوص، عمليات، تعليقات، whitespace، newlines، أحرف غير صالحة.
- **Parser:** متغيرات، تعبيرات، شروط، تكرارات، أولويات، أخطاء صياغة.
- **Diagnostics:** line، column، snippet، error code، رسالة عربية مقروءة.
- **Integration:** `خلي س = 10` / `خلي ص = 20` / `اطبع س + ص` → `30`.
- **Regression:** إخراج `test.masr` الذهبي حرفيًا (12 سطر) بعد التحويل إلى `.arb`.

### 7.3 قواعد كتابة الاختبارات
- لا اختبارات بلا توقعات محدّدة (لا `assert True`).
- كل اختبار يبدأ من **مصدر نصي واحد** (مستوى المستخدم) إلا اختبارات الوحدة الصريحة (positions/environment).
- `mypy --strict` على `al_arabiya/`، `ruff check` على المشروع كله.

---

## 8. Out of Scope (خارج Phase 1)

لا يُنفَّذ الآن (لكن البنية جاهزة استقباله): Type System، Functions (الـ environment chain والـ parser جاهزان)، Structs/Enums، Modules، Stdlib، Bytecode VM، Native/LLVM، Package Manager، LSP، VS Code Extension، Debugger، Generics، Async، AI Agents/Workflows.

## 9. معايير النجاح (Definition of Done)

- [ ] لا يعتمد المشروع على `masry.py` كملف مركزي (مرجعي فقط في `legacy/`).
- [ ] كل مكوّن في موديول مستقل بواجهة موثّقة + type hints.
- [ ] `arabic run` / `arabic check` / `arabic repl` تعمل.
- [ ] كل الأمثلة القديمة تعمل وخرجاتها **مطابقة حرفيًا** للذهبي.
- [ ] اختبارات لكل طبقة (lexer/parser/ast/diagnostics/interpreter/cli/integration/regression) وخالية من الفشل.
- [ ] Diagnostics: كود + موقع (line/column) + snippet + رسالة عربية + severities.
- [ ] README + docs/language + docs/architecture + docs/development محدّثة للهوية الجديدة.
- [ ] `ruff` و`mypy` و`pytest` خضراء.
