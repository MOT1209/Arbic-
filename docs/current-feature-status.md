<div dir="rtl">

> **تحديث بعد الدمج:** هذا المستند لقطة تاريخية للكود عند `f338e9e` (Phase 0). بعد دمج `origin/main` (المراحل 2–8) اللغة بقت فيها دوال، قوائم/قواميس، وحدات، استثناءات، فحص أنواع، LSP، VM، ومدير حزم. للوضع الحالي راجع `README.md` و`docs/language/syntax.md`.



# حالة الميزات الحالية — Arbic / AlArabiya

> **آخر تحديث:** 2026-11-08 (Phase 0)
> **قاعدة:** لا تُصنَّف ميزة «منفّذة» إلا إذا كان لها كود + اختبار ناجح. كل صنف أدناه مسنود إلى ملف أو اختبار.

## دليل الرموز

| الرمز | المعنى |
|---|---|
| ✅ | منفّذة ومختبَرة |
| 🟡 | جزئية أو داخلية فقط |
| 🧪 | تجريبية (تعمل لكن ليست جزءًا من العقد اللغوي) |
| ⛔ | غير منفّذة |

---

## 1. اللغة — البنية الأساسية

| الميزة | الحالة | الدليل |
|---|---|---|
| متغيرات بتعريف صريح `خلي` | ✅ | `parser._parse_declaration`، اختبارات interpreter |
| إعادة إسناد `اسم = قيمة` | ✅ | `parser._parse_assignment` |
| تعريف ضمني عند الإسناد | 🟡 | يعمل مع تحذير `W3001` + `Environment.define` |
| ثوابت (`const`) | ⛔ | لا keyword ولا عقدة AST |
| طباعة `اطبع` | ✅ | `PrintStatement` |
| شروط `لو` / `غير كده` / `خلاص` | ✅ | `IfStatement` |
| `غير كده لو` (else-if) | ⛔ | اختبار تكاملي يؤكد فشلها `test_fizzbuzz_style_condition_chain` |
| حلقة عددية `كرر N مرات` / `مرة` | ✅ | `RepeatStatement` |
| حلقة شرطية `طالما` | ✅ | `WhileStatement` + حارس 1,000,000 دورة (`E4005`) |
| `break` / `continue` | ⛔ | لا keywords |
| دوال معرّفة من المستخدم | ⛔ | لا `دالة`، لا استدعاء، لا `رجّع` |
| استدعاء دالة | ⛔ | لا parselet للاستدعاء |
| نطاقات كتل حقيقية | ⛔ | الـ Interpreter يستخدم نطاقًا عالميًا واحدًا؛ `Environment.child()` موجودة لكن غير مستخدمة |
| تعليقات `#` | ✅ | `lexer._scan_token` |
| فاصل أوامر = سطر جديد | ✅ | `Parser._end_statement` |

## 2. التعبيرات والعوامل

| الميزة | الحالة | الدليل |
|---|---|---|
| جمع/طرح/ضرب/قسمة/باقي (`+ - * / %`) | ✅ | `test_expression_matrix` |
| مرادفات عربية (`زائد ناقص في على`) | ✅ | `test_word_operators` |
| مقارنات رمزية (`== != < > <= >=`) | ✅ | `test_symbolic_comparisons` |
| مقارنات عربية (`أكبر من`، `أصغر أو يساوي`، `يساوي`، `مش يساوي`) | ✅ | `test_arabic_comparison_words` وغيرها |
| منطق `و` / `أو` مع short-circuit | ✅ | ترجّع `bool` دائمًا (وليس قيمة الطرف) |
| سالب أحادي `-` و`ناقص` | ✅ | `UnaryExpression` |
| أولويات حسابية صحيحة | ✅ | precedence climbing |
| أقواس grouping | 🟡 | تعمل؛ لكن `span` العقدة الداخلية لا يشمل القوسين |
| لصق نص + رقم بـ `+` | ✅ | `test_string_concatenation` («العمر: 25») |
| فهرسة `[...]` | ⛔ | الرمز يُlex لكن لا parser |
| وصول عضو `.` | ⛔ | الرمز يُlex لكن لا parser |
| استدعاء `(...)` | ⛔ | الأقواس للتجميع فقط |
| سلسلة نصية داخلية (interpolation) | ⛔ | لا صياغة محددة |
| تعبير يمتد على عدة أسطر | ⛔ | الفحص أثبت E2002؛ التوثيق يدّعي العكس |

## 3. القيم والأنواع

| الميزة | الحالة | الدليل |
|---|---|---|
| أعداد صحيحة `int` | ✅ | `Literal.value` |
| أعداد عشرية `float` | ✅ | `12.5`، `١٢٫٥` |
| نصوص `str` | ✅ | مع escapes |
| منطقي `صح` / `غلط` | ✅ | `KW_TRUE` / `KW_FALSE` |
| `None` / `شي` | ⛔ | `Value = int \| float \| str \| bool` فقط |
| `قائمة` / `قاموس` / `مجموعة` / `صف` | ⛔ | لا عقد AST ولا قيم وقت تشغيل |
| أي تعليقات أنواع (`أ: عدد`) | ⛔ | لا parser للأنواع |
| نظام أنواع ساكن | ⛔ | لا type checker |

## 4. الأرقام والنصوص

| الميزة | الحالة | الدليل |
|---|---|---|
| أرقام عربية-هندية `٠-٩` | ✅ | `_DIGIT_MAP` |
| أرقام فارسية `۰-۹` | ✅ | `_EXTENDED_ARABIC_INDIC_DIGITS` |
| فاصلة عشرية عربية `٫` | ✅ | `_DECIMAL_SEPARATOR` |
| فاصل آلاف `٬` يُتجاهل | ✅ | `_THOUSANDS_SEPARATOR` |
| escapes: `\n \t \r \0 \\ \" \'` | ✅ | `_SIMPLE_ESCAPES` |
| escape يونيكود `\u{XXXX}` | ✅ | `_scan_unicode_escape` |
| نص غير مغلق → `E1002` | ✅ | `test_unterminated_string_reports_error` |
| رقم فاسد `1..2` → `E1004` | ✅ | يُبلَّغ ثم يُستأنف بقيمة مصححة |
| أعداد سالبة/كسرية في `كرر` | 🟡 | تُقبل بصمت: `-2` → صفر دورات، `2.9` → دورتان |

## 5. التشخيصات

| الميزة | الحالة | الدليل |
|---|---|---|
| `Diagnostic` بكود + شدة + Span + اقتراح | ✅ | `diagnostics/diagnostics.py` |
| تجميع عدة أخطاء في تمريرة واحدة | ✅ | panic recovery + `DiagnosticBag` |
| إزالة التكرار وحد أقصى | ✅ | `test_bag_deduplicates` / `test_bag_limit` |
| عرض عربي بكود وموقع وسطر وcarets | ✅ | `test_render_contains_all_required_parts` |
| Severity: خطأ/تحذير/معلومة/تلميح | ✅ | `Severity` (INFO/HINT معرّفة لكن لا تُستخدم) |
| مواضع على code points | ✅ | `test_position_offset_and_length` |
| أخطاء دلالية/أنواع قبل التشغيل | ⛔ | لا semantic analyzer |
| كتالوج أكواد مطابق للتوثيق | ⛔ | التوثيق يخالف `errors.py` (انظر `technical-debt.md`) |

## 6. التشغيل

| الميزة | الحالة | الدليل |
|---|---|---|
| مفسّر شجري (tree-walking) | ✅ | `Interpreter(ASTVisitor)` |
| مخرجات `صح`/`غلط` بالعربية | ✅ | `format_value` |
| طباعة `3.0` كـ `3` | ✅ | `format_value` |
| قسمة على صفر → `E4002` | ✅ | `test_division_by_zero_error` |
| متغير غير معرّف → `E4001` | ✅ | `Environment.get` |
| خطأ نوع → `E4003` | ✅ | `_type_error` |
| حارس حلقة لا نهائية → `E4005` | ✅ | `test_loop_guard` |
| bytecode VM | ⛔ | لا وجود |
| IR / optimizer | ⛔ | لا وجود |
| Python interop | ⛔ | لا existence |
| معالجة استثناءات للمستخدم | ⛔ | لا `محاولة/امسك` |
| async/await | ⛔ | لا وجود |
| generators/iterators | ⛔ | لا وجود |

## 7. الوحدات والبرامج

| الميزة | الحالة | الدليل |
|---|---|---|
| ملف واحد لكل برنامج | ✅ | CLI يقرأ ملفًا واحدًا |
| `استورد` / وحدات | ⛔ | لا parser ولا runtime |
| مشروع متعدد الملفات | ⛔ | لا build system |
| مكتبة قياسية | ⛔ | لا `مكتبة.*` |
| مدير حزم | ⛔ | لا `install`/`build`/`doctor` |
| playground | ⛔ | لا وجود |
| LSP / VS Code / debugger / formatter | ⛔ | لا وجود |

## 8. CLI

| الأمر | الحالة | ملاحظات |
|---|---|---|
| `arabic run <file>` | ✅ | exit 0/1/2 |
| `arabic check <file>` | ✅ | لا ينفّذ |
| `arabic` / `arabic repl` | ✅ | `خروج` / `exit` / `quit` |
| `arabic version` | ✅ | `arabic 0.1.0` |
| `arabic help` / `-h` / `--help` | ✅ | |
| `arabic init` | ⛔ | |
| `arabic build` | ⛔ | |
| `arabic test` | ⛔ | |
| `arabic format` | ⛔ | |
| `arabic install` / `remove` / `update` / `search` / `publish` / `list` / `doctor` | ⛔ | |

**أكواد الخروج الفعلية:** `0` نجاح، `1` خطأ لغوي (ترجمة أو تشغيل)، `2` خطأ استخدام/ملف.

## 9. الاختبارات والجودة

| البند | الحالة |
|---|---|
| اختبارات وحدة لكل طبقة | ✅ 211 اختبار (منها 11 اختبار عقود) |
| اختبارات تكامل | ✅ 16 |
| اختبارات رجعية مقابل `legacy/masry.py` | ✅ 7 برامج × مسارين |
| ruff + mypy strict | ✅ |
| CI | ⛔ |
| property-based / fuzz | ⛔ |
| security tests | ⛔ |
| benchmarks | ⛔ |
| differential tests (Interpreter vs VM) | ⛔ (لا VM) |

## 10. ما يجب ألا يفترضه أحد

هذه العناصر **غير موجودة** رغم أن خارطة 2.0 تهدف إليها:

> الدوال، `رجّع`، الفئات، الوراثة، الواجهات، lambda، decorators، pattern matching، generics، union/optional types، type inference، `استورد`، المكتبة القياسية، `قائمة`/`قاموس`، `شي`/None، الاستثناءات للمستخدم، async/await، generators، package manager، LSP، formatter، debugger، playground، Python interop، IR، optimizer، bytecode، VM.

أي برنامج يستخدم أيًا منها سيفشل اليوم بخطأ `E2002` أو `E4001`، وليس بميزة ناقصة الصياغة.

</div>
