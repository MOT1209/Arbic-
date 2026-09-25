<div dir="rtl">

# دليل التطوير

## المتطلبات

- Python 3.12+ (اتجرب على 3.14)
- `pip install -e .` — ينصّب الباكتيج + أمر `arabic`
- أدوات الفحص: `pytest` · `ruff` · `mypy`

```bash
pip install -e ".[dev]"
python tools/check.py      # pytest + ruff + mypy مع بعض
```

---

## بنية المشروع

```
al_arabiya/
├── __main__.py            # python -m al_arabiya
├── compiler/
│   ├── positions.py       # Position / Span
│   ├── diagnostics/       # SourceFile, ErrorCode, Diagnostic, DiagnosticBag
│   ├── lexer/             # TokenType, KEYWORDS, Lexer
│   ├── parser/            # precedence.py + Parser (Pratt / precedence climbing)
│   ├── ast/               # nodes (dataclass) + visitor
│   └── frontend.py        # compile_source() → FrontendResult
├── runtime/
│   └── interpreter/       # Environment, Interpreter
└── cli/                   # main.py (أوامر) + repl.py (REPL)
legacy/masry.py            # المترجم القديم (للرجوعية)
tests/                     # 200 اختبار (unit + integration + regression)
```

---

## أوامر سريعة

```bash
arabic run مثال.arb           # تشغيل
arabic check مثال.arb         # فحص بدون تشغيل
arabic repl                   # تفاعلي
pytest                        # كل الاختبارات
pytest tests/lexer            # طبقة واحدة
pytest -k short_circuit       # اختبار بالاسم
ruff check . --fix            # lint + إصلاح تلقائي
mypy                          # أنواع صارمة (strict)
```

---

## امتدادات مضافة (كيف تضيف ميزة)

1. **كلمة مفتاحية جديدة** → أضفها في `KEYWORDS` + `TokenType` + `token_kind_of` (لو keyword) في `lexer/tokens.py`.
2. **عامل/أوّلية جديدة** → `parser/precedence.py` + سطر في `_peek_infix`/`_peek_prefix`.
3. **أمر جديد** → case جديد في `parse_statement`.
4. **عقدة AST** → `dataclass` جديد في `ast/nodes.py` + زر في `visit_*` بالـ interpreter (وأي دوال `check_*`).
5. **كود خطأ** → أضف في `ErrorCode` (بنمط `E####`) واستخدمه.

بعد أي تعديل شغّل `python tools/check.py` — لازم يفضل **200/200** واختبارات الرجوعية (goldens) مطابقة.

---

## اختبارات الرجوعية

`tests/regression/` فيه 7 برامج `programs/*.arb` + مخرجاتها `expected/*.txt` **اللي اتولّدت من `legacy/masry.py`**. الاختبار بيشغّل البرنامج الحالي ومقارن السطور بالظبط (ولو الملف `.masr` شغّله بنفس goldens). عشان تولّد goldens جديدة:

```bash
python -X utf8 tools/gen_goldens.py   # لو موجود، أو عدّل يدويًا بعد مراجعة الفرق
```

**القاعدة**: ما تغيّرش goldens لمجرد إن الجديد "أصح" — افهم الفرق الأول.

---

## اصطلاحات

- كود Lint: `ruff` (E,F,W,I,UP,B) بطول سطر 100 — `legacy/` مستثنا.
- أنواع: `mypy --strict` على `al_arabiya/` بس.
- التعليقات/رسائل الأخطاء: بالعربي.
- الملفات الجديدة: كل الـ strings Unicode-safe — استخدم `python -X utf8` لو طلعت mojibake في الطرفية.
- مفيش `print()` أثناء التطوير — استخدم `DiagnosticBag`.

</div>
