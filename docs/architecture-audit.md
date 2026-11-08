<div dir="rtl">

> **تحديث بعد الدمج:** هذا المستند لقطة تاريخية للكود عند `f338e9e` (Phase 0). بعد دمج `origin/main` (المراحل 2–8) اللغة بقت فيها دوال، قوائم/قواميس، وحدات، استثناءات، فحص أنواع، LSP، VM، ومدير حزم. للوضع الحالي راجع `README.md` و`docs/language/syntax.md`.



# تدقيق البنية — Arbic / AlArabiya

> **ملاحظة:** ده تدقيق Phase 0؛ أوامر `build`/`test`/`format` والعازل الجزئي (`--sandbox`) اتضافوا بعد اللقطة دي. الحالة الحالية في `docs/current-feature-status.md`.

> **المرحلة:** Phase 0 — تدقيق المستودع وتثبيت خط الأساس
> **التاريخ:** 2026-11-08
> **المرجع:** الكود الفعلي في المستودع. كل ادعاء هنا مسنود إلى ملف أو أمر تم تشغيله، وليس إلى الماستر برومبت.

---

## 1. المنهج

تم تنفيذ الأوامر التالية على المستودع كما هو، دون أي تعديل على الكود:

```bash
python -m pytest -q            # 200 اختبار
python -m ruff check .         # All checks passed
python -m mypy                 # Success: no issues found in 25 source files
python -m al_arabiya check examples/*.arb
```

بالإضافة إلى فحص يدوي لكل ملفات `al_arabiya/` و`tests/` و`docs/`، و4 فحوص سلوكية مباشرة (انظر §9) للتحقق من ادعاءات التوثيق.

---

## 2. الملخص التنفيذي

1. **المشروع الحالي مترجم/مفسّر تعليمي صغير، وليس نسخة جزئية من Arbic 2.0.** الموجود فعليًا هو: Lexer + Parser + AST + Diagnostics + Interpreter شجري + CLI/REPL. لا يوجد أي مكوّن من الطبقات المتقدمة (Semantic Analysis، Type Checker، IR، Optimizer، Codegen، VM، Stdlib، Package Manager، LSP، Formatter، Debugger).
2. **خط الأساس أخضر بالكامل:** 200/200 اختبار ناجح، `ruff` نظيف، `mypy --strict` نظيف على 25 ملف مصدر. هذا خط أساس موثوق للبدء.
3. **أكبر فجوة وظيفية ليست OOP ولا الأنواع، بل الدوال.** اللغة لا تحتوي على دالة معرّفة من المستخدم، ولا `رجّع`، ولا استدعاء. أي حديث عن OOP أو Generics أو IR قبل الدوال سيكون بناءً على أساس غائب.
4. **التوثيق يتقدّم على الواقع في مواضع محددة** (4 ادعاءات تم إثبات عدم صحتها، §9). هذه أخطر مشكلة هندسية لأنها تجعل أي وكيل أو مطوّر يبني على سلوك غير موجود.
5. **خطر أمني فوري:** سبعة ملفات غير متتبعة في جذر المستودع، منها `cmdkey_all.txt` بحجم 5,748 بايت، وليست مستثناة في `.gitignore`. لم تُقرأ محتوياتها في هذا التدقيق (قد تحتوي أسرارًا)، لكن وجودها يعني خطر تسريب عند أي `git add .`.
6. **لا يوجد CI.** لا مجلد `.github`، وأوامر الجودة تعمل محليًا فقط.

---

## 3. الشجرة الفعلية

```text
arbic/
├── al_arabiya/
│   ├── __init__.py            # __version__ = "0.1.0"، LANGUAGE_NAME = "العربية"
│   ├── __main__.py            # python -m al_arabiya
│   ├── compiler/
│   │   ├── frontend.py        # compile_source / compile_text → FrontendResult
│   │   ├── lexer/
│   │   │   ├── positions.py   # Position / Span (code points)
│   │   │   ├── tokens.py      # TokenType + KEYWORDS + Token
│   │   │   └── lexer.py       # Unicode-safe scanner + escape/number handling
│   │   ├── parser/
│   │   │   ├── precedence.py  # Precedence IntEnum
│   │   │   └── parser.py      # recursive descent + precedence climbing + panic recovery
│   │   ├── ast/
│   │   │   ├── nodes.py       # dataclasses + iter_child_nodes
│   │   │   └── visitor.py     # ASTVisitor + iter_walk
│   │   └── diagnostics/
│   │       ├── source.py      # SourceFile + lazy line indexing
│   │       ├── errors.py      # ErrorCode + exception bridge
│   │       └── diagnostics.py # Diagnostic / DiagnosticBag / Arabic renderer
│   ├── runtime/
│   │   └── interpreter/
│   │       ├── environment.py # Environment (parent chain) + Value alias
│   │       └── interpreter.py # ASTVisitor implementation
│   └── cli/
│       ├── main.py            # run / check / repl / version / help
│       └── repl.py            # multi-line REPL
├── tests/                     # 9 ملفات اختبار + conftest = 211 اختبار
├── tests/regression/programs/ # 7 برامج (.arb + .masr)
├── tests/regression/expected/ # 7 مخرجات ذهبية
├── examples/                  # 4 برامج .arb
├── docs/                      # 3 مستندات (قبل هذا التدقيق)
├── legacy/masry.py            # 526 سطرًا — مرجع رجعي فقط
├── tools/check.py             # ruff + mypy + pytest
├── pyproject.toml             # hatchling، entry point: arabic
└── README.md
```

**ملاحظة:** لا توجد مجلدات `semantic/`، `type_checker/`، `ir/`، `optimizer/`، `codegen/`، `vm/`، `stdlib/`، `packages/`، `lsp/`، `debugger/`، `formatter/`، ولا `scripts/`، ولا `vscode-extension/`، ولا `playground/`.

---

## 4. خط الأنابيب الفعلي

```text
نص المصدر (UTF-8)
        │
        ▼
    Lexer.tokenize()  ──────────────► DiagnosticBag  (E1xxx)
        │  list[Token] + EOF
        ▼
    Parser.parse_program() ─────────► DiagnosticBag  (E2xxx + panic recovery)
        │  Program AST (كل عقدة تحمل Span)
        ▼
    Interpreter.run()  ─────────────► DiagnosticBag  (W3001) + ArabiyaRuntimeError (E4xxx)
        │
        ▼
    write(value)  → stdout
```

الفصل بين الطبقات **متحقق فعلًا**:

| الثابت المعماري | الحالة | الدليل |
|---|---|---|
| الـ Lexer لا يعرف Parser ولا Runtime | ✅ | `lexer/lexer.py` يستورد diagnostics + tokens فقط |
| الـ Parser لا ينفّذ ولا يعرف Runtime | ✅ | `parser/parser.py` يستورد AST + diagnostics + tokens |
| الـ Interpreter يرى AST فقط | ✅ | `runtime/interpreter/interpreter.py` لا يستورد lexer/parser |
| كل خطأ لغوي = `Diagnostic` وليس traceback | ✅ | المسار الكامل عبر `DiagnosticBag`؛ الاختبارات تتحقق من الأكواد |
| لا حالة عامة قابلة للتغيير | ✅ | كل حالة داخل كائنات `Lexer` / `Parser` / `Interpreter` / `Environment` |
| الـ frontend قابل للاستدعاء بدون تنفيذ | ✅ | `compile_source` تُستخدم في `check` و LSP لاحقًا |

**نقطة انحراف موثّقة عن المعمارية المستهدفة:** الـ diagnostics موجودة تحت `compiler/diagnostics/` بدل أن تكون طبقة مستقلة، لكنها لا تستورد أي شيء من lexer/parser سوى `Position`، لذا الفصل مقبول حاليًا.

---

## 5. مقارنة بالمعمارية المستهدفة

| المكوّن المستهدف | الحالة الفعلية | الدليل / الملاحظة |
|---|---|---|
| `compiler/lexer` | ✅ موجود | 36 اختبار lexer |
| `compiler/parser` | ✅ موجود (لغة صغيرة) | 42 اختبار parser |
| `compiler/ast` | ✅ موجود | 10 اختبارات AST + spans |
| `compiler/semantic` | ⛔ غير موجود | لا مجلد ولا symbol table |
| `compiler/type_checker` | ⛔ غير موجود | لا نوع إلا في وقت التشغيل |
| `compiler/ir` | ⛔ غير موجود | لا تمثيل وسيط |
| `compiler/optimizer` | ⛔ غير موجود | — |
| `compiler/codegen` | ⛔ غير موجود | — |
| `runtime/interpreter` | ✅ موجود | 41 اختبار مفسّر |
| `runtime/memory` | ⛔ غير موجود | إدارة ذاكرة Python؛ لا نموذج ملكية موثّق |
| `runtime/modules` | ⛔ غير موجود | لا `استورد` |
| `runtime/exceptions` | 🟡 داخلي فقط | `ArabiyaRuntimeError` لأخطاء التنفيذ؛ لا `محاولة/امسك` للمستخدم |
| `runtime/concurrency` | ⛔ غير موجود | لا async/await |
| `runtime/interop` | ⛔ غير موجود | لا جسر Python |
| `vm/*` | ⛔ غير موجود | لا bytecode ولا VM |
| `stdlib/*` | ⛔ غير موجود | لا `مكتبة.*` |
| `packages/*` | ⛔ غير موجود | لا package manager |
| `lsp/` | ⛔ غير موجود | لا server |
| `debugger/` | ⛔ غير موجود | لا breakpoints ولا DAP |
| `formatter/` | ⛔ غير موجود | لا formatter |
| `cli/` | 🟡 جزئي | 5 أوامر فقط: `run`، `check`، `repl`، `version`، `help` |
| `tests/security`، `tests/benchmarks` | ⛔ غير موجود | لا اختبارات أمنية ولا قياسات أداء |
| CI | ⛔ غير موجود | لا `.github/workflows` |
| Docs | 🟡 جزئي + انحراف | 3 مستندات؛ 4 ادعاءات غير صحيحة |

---

## 6. القياسات الفعلية (خط الأساس)

### 6.1 الاختبارات

| المجموعة | العدد | الملاحظة |
|---|---:|---|
| `tests/ast` | 10 | بنية العقد والـ spans |
| `tests/cli` | 23 | أوامر، أكواد خروج، REPL |
| `tests/diagnostics` | 16 | الـ bag والعارض العربي |
| `tests/integration` | 16 | برامج كاملة من المصدر للمخرجات |
| `tests/interpreter` | 41 | عبارات، تعبيرات، بيئة، أخطاء تشغيل |
| `tests/lexer` | 36 | معرّفات، أرقام، نصوص، مواقع، أخطاء |
| `tests/parser` | 42 | عبارات، أولويات، أخطاء صياغة |
| `tests/regression` | 16 | 7 برامج × (ذهبي + مقارنة legacy) + اختباران |
| `tests/contracts` | 11 | عقود أكواد الخطأ وأكواد الخروج (أُضيفت في Phase 1) |
| **الإجمالي** | **211** | **كلها ناجحة** (verified) |

كان الإجمالي 200 عند تدقيق Phase 0؛ أضافت Phase 1 أحد عشر اختبار عقود.

### 6.2 الجودة

| الفحص | النتيجة |
|---|---|
| `pytest` | 211 passed |
| `ruff check .` | All checks passed |
| `mypy` (strict على `al_arabiya/`) | no issues found in 25 source files |
| `arabic check examples/*.arb` | 4/4 سليمة |

### 6.3 ما لم يُقس

- لا قياسات أداء (زمن بدء، زمن ترجمة، زمن تنفيذ، ذاكرة).
- لا اختبارات fuzz أو property-based.
- لا اختبارات أمنية.
- لا تشغيل على CI متعدد المنصات. كل النتائج أعلاه من بيئة تطوير واحدة (Windows).

---

## 7. الهوية والتسمية — انحراف يحتاج قرارًا

| البند | في الماستر برومبت | في المستودع |
|---|---|---|
| اسم المشروع | Arbic / AlArabiya | `AlArabiya` / `العربية` |
| الإصدار | 2.0 | `0.1.0` |
| المستودع | `MOT1209/Arbic-` | `ahmedfox1/masry` في README و`pyproject.toml` |
| الحزمة | — | `al-arabiya` (PyPI/hatchling) |
| الأمر | `arabic` | `arabic` ✅ |
| الامتداد | `.arb` | `.arb` ✅ (و`.masr` مقروء رجعيًا) |

الخلاف ليس شكليًا: تغيير اسم الحزمة أو الأمر أو الامتداد يكسر المستخدمين الحاليين. **لا يُنفَّذ أي تغيير هوية قبل تسجيل ADR.** (انظر §11.)

---

## 8. نقاط القوة التي يجب الحفاظ عليها

1. **الـ Diagnostics نظام حقيقي:** كود + شدة + Span + اقتراح عربي + عرض بالـ carets. هذا أساس جاهز لـ LSP وVM لاحقًا.
2. **الـ Span يُحسب على code points**، لا على bytes — ضروري للعربية وRTL.
3. **Pratt parser مع panic recovery** — إضافة عوامل أو استدعاءات أو فهرسة لاحقًا ممكنة دون إعادة كتابة.
4. **الـ Environment يدعم سلسلة Scopes** (parent chain) رغم أن الـ Interpreter الحالي لا يستخدم إلا نطاقًا واحدًا. البنية جاهزة للدوال.
5. **اختبارات الرجعية تقارن بـ `legacy/masry.py` نفسه** عبر subprocess، لا بالـ goldens فقط — حماية قوية ضد انحراف غير مقصود.
6. **`mypy --strict` ناجح** مع dataclasses وslots؛ هذا يقلل تكلفة التوسعة.

---

## 9. نتائج الفحص السلوكي مقابل التوثيق

كل نتيجة أدناه ناتجة عن تشغيل فعلي في هذه الجلسة.

| # | الادعاء في التوثيق | السلوك الفعلي | الحكم |
|---|---|---|---|
| 1 | `docs/language/syntax.md` §1: الأقواس المفتوحة تلغي معنى السطر الجديد، فالتعبير يمكن أن يمتد لعدة أسطر داخل `( )` | `اطبع (1 +` ثم سطر `2)` → **E2002** عند السطر 1 العمود 10 («محتاج تعبير هنا بس لقيت نهاية السطر») | ❌ غير صحيح |
| 2 | `syntax.md` §2: القيمة `شي` = `None` | `خلي س = شي` → **E4001** «المتغير 'شي' مش معرّف» | ❌ غير موجودة |
| 3 | `syntax.md` §3: `و`/`أو` ترجّع قيمة (سلوك Python) لا بالضرورة `صح`/`غلط` | `اطبع "أ" و "ب"` → `صح`، و`اطبع 0 و 3` → `غلط` | ❌ ترجّع `bool` دائمًا |
| 4 | `syntax.md` §6: جدول أكواد الأخطاء | الجدول يخالف `errors.py` في 9 صفوف، وينقصه `E4004` و`E4005`، ويقول إن حارس الحلقة `E4003` بينما هو `E4005` | ❌ غير مطابق |
| 5 | `docs/architecture/phase-1-analysis.md` §4.5: أكواد الخروج `0/1/2/3` مع تمييز خطأ التشغيل | `cli/main.py` وREADME: `0` نجاح، `1` خطأ لغوي (ترجمة **أو** تشغيل)، `2` استخدام/ملف | ❌ غير مطابق |
| 6 | `docs/development/guide.md`: مسار `compiler/positions.py` | المسار الفعلي `compiler/lexer/positions.py` | ❌ غير مطابق |
| 7 | `guide.md`: أضف keyword عبر `token_kind_of` | لا توجد دالة بهذا الاسم في المستودع | ❌ غير موجودة |
| 8 | `guide.md`: `tools/gen_goldens.py` | `tools/` يحتوي `check.py` فقط | ❌ غير موجود |
| 9 | `README.md` و`pyproject.toml`: المستودع `github.com/ahmedfox1/masry` | المشروع المطلوب `MOT1209/Arbic-` | ❌ قديم |
| 10 | `README.md`: «200 اختبار» | 200 passed | ✅ صحيح |
| 11 | `guide.md`: 7 برامج رجعية | 7 ملفات في `tests/regression/programs/` | ✅ صحيح |
| 12 | `README.md`:Phase 1 بلا دوال وهياكل بيانات | لا دوال ولا مجموعات بيانات | ✅ صحيح |

**تحديث Phase 1:** الانحرافات من 1 إلى 9 اتصلحت، و`tests/contracts/` بتمنع رجوعها.

**ملاحظة إضافية (وقت التدقيق):** `README.md` يحتوي نصًا تالفًا (أحرف CJK داخل كلمة «escape») وثلاثة أسطر `"# Arbic-"` بعد وسم الإغلاق. و`syntax.md` يعرض `E1003` كـ«رقم غير صالح» بينما هو `INVALID_ESCAPE`.

---

## 10. المخاطر

| # | الخطر | الشدة | التفصيل |
|---|---|---|---|
| R1 | تسريب أسرار | **حرجة** | `cmdkey_all.txt` (5,748 بايت) و`gh_login_err.txt` و`gh_code_err.txt` و`push_err.txt` غير متتبعة وغير مستثناة في `.gitignore` |
| R2 | بناء على سلوك موثّق غير موجود | عالية | 4 ادعاءات غير صحيحة في `syntax.md`؛ أي وكيل قادم قد يبني عليها |
| R3 | غياب CI | عالية | لا حماية من الانحدار عند الدمج |
| R4 | لا دوال/وحدات/مجموعات | عالية | تمنع OOP وStdlib وIR وVM — كل خطة لاحقة تعتمد عليها |
| R5 | النطاق العالمي الواحد | متوسطة | المتغيرات تعيش خارج الكتل؛ تغييره لاحقًا سلوك كاسر ويحتاج سياسة توافق |
| R6 | REPL heuristic | متوسطة | يعتمد على عمق الأقواس + خطأ عند نهاية الإدخال؛ لا اختبار لنِسَب متداخلة معقدة |
| R7 | `repeat` يقبل أعدادًا سالبة وكسرية بصمت | متوسطة | `كرر -2 مرات` ينفّذ صفر مرة، و`كرر 2.9 مرات` ينفّذ مرتين، بلا تشخيص |
| R8 | غياب قياسات أداء | منخفضة | أي ادعاء تحسين لاحقًا سيكون بلا دليل |
| R9 | أسماء بايثون العامة | منخفضة | الحزمة `al_arabiya` موحّدة، فلا تعارض حزم |

---

## 11. قرارات معمارية مطلوبة (ADRs)

تُسجَّل قبل تنفيذ أي مرحلة لاحقة، لا أثناءها:

1. **ADR-01 — الهوية:** هل الاسم النهائي `Arbic` أم `AlArabiya`؟ وما fate الحزمة `al-arabiya` والأمر `arabic` والامتداد `.masr`؟ (تغيير الاسم الآن أرخص من تغييره بعد Stdlib وPackage Registry.)
2. **ADR-02 — نطاق الكتل:** هل تبقى المتغيرات عالمية (توافق 0.1) أم تُفعَّل Scopes عند إضافة الدوال؟ وما سياسة التوافق للبرامج القديمة؟
3. **ADR-03 — عقد أكواد الأخطاء:** `errors.py` هو المصدر الوحيد للحقيقة؛ التوثيق يُولَّد أو يُفحص آليًا ضدّه.
4. **ADR-04 — أمان interop:** أي استدعاء Python غير موثوق يجب أن يكون في عملية معزولة بحدود موارد، لا عبر allowlist داخل نفس العملية.
5. **ADR-05 — نموذج VM:** Stack-based أم Register-based؟ (يُحسم قبل كتابة أول تعليمة bytecode، لا بعدها.)
6. **ADR-06 — ثقة الحزم:** checksums + توقيعات + سياسة استخراج آمن (رفض symlink/path traversal) قبل نشر أي registry.

---

## 12. تقرير التطوير — Phase 0

### المنجز

- قراءة كاملة لمصدر المشروع (25 ملف مصدر + 8 ملفات اختبار + 3 مستندات + 4 أمثلة + legacy).
- تشغيل بوابات الجودة الثلاث وتسجيل النتائج الفعلية.
- 12 فحصًا للتوثيق مقابل السلوك، منها 9 انحرافات موثّقة.
- إنتاج مستندات المرحلة الأربعة + تقرير التطوير.

### الملفات المضافة

- `docs/architecture-audit.md` (هذا الملف)
- `docs/current-feature-status.md`
- `docs/technical-debt.md`
- `docs/arbic-2.0-roadmap.md`
- `docs/development/report-phase-0.md`

### الملفات المعدّلة

- لا شيء. لم يُمس أي كود أو اختبار أو مستند قائم (شرط Phase 0: لا تغييرات تدميرية).

### الاختبارات المنفذة

```text
python -m pytest -q          → 200 passed
python -m ruff check .       → All checks passed
python -m mypy               → Success: no issues found in 25 source files
python -m al_arabiya check examples/*.arb → 4/4 سليمة
```

### المشاكل المعروفة

- كل ما ورد في §9 و§10.

### الخطوة التالية

Phase 1 — تثبيت الأساس والأمان: إصلاح انحراف التوثيق، إضافة CI، معالجة ملفات الاعتماد، تثبيت عقد أكواد الخروج والأخطاء، وتوسيع اختبارات الرجعية. التفاصيل في `docs/arbic-2.0-roadmap.md`.

</div>
