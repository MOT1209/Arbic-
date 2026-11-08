<div dir="rtl">

# المساهمة

## الإعداد

```bash
git clone https://github.com/MOT1209/Arbic-.git
cd Arbic-
python -m venv .venv
pip install -e ".[dev]"
```

بيحتاج Python 3.12 أو أحدث.

## البوابات قبل أي دفع

```bash
python tools/check.py     # pytest + ruff + mypy مع بعض
```

- `ruff check .` — قواعد `E,F,W,I,UP,B` بطول سطر 100 (`legacy/` مستثنى).
- `mypy` — وضع `strict` على `al_arabiya/` بس.
- `pytest` — لازم كله أخضر، ومفيش اختبارات متخطّاة جديدة.
- **الأمثلة:** كل ملف في `examples/*.arb` لازم يعدّي `arabic check`.

CI بيشغّل نفس البوابات على Ubuntu وWindows × Python 3.12/3.13/3.14. أي أحمر في CI بيوقف الدمج.

## قواعد التغيير

1. **مفيش ميزة بدون اختبار.** أي سلوك جديد لازم يكون له اختبار وحدة (وأحيانًا تكامل ورجعية) في نفس الكوميت.
2. **كود خطأ جديد** → أضفه في `ErrorCode` **وحدّث جدول §6 في `docs/language/syntax.md`**. `tests/contracts/test_contracts.py` هيفشل لو الجدول والـ enum مش متطابقين، أو لو كود مش مستخدم في أي مكان.
3. **تغيير سلوك** → وثّقه، واكتب ADR في `docs/architecture/` لو القرار مؤثر، وأضف اختبار يثبّت السلوك الجديد. البرامج القديمة تفضل شغالة إلا لو الكسر مقصود وموثّق.
4. **الوثائق جزء من التغيير:** أي تعديل في النحو أو الأكواد أو المكتبة لازم يلمس `docs/language/` (أو `docs/tools/`) في نفس الكوميت.
5. **الرسائل بالعربي** زي باقي الكود، وبنفس المصطلحات المستقرة.
6. **مفيش force-push** على `main`، ومفيش دفع مباشر لتغيير كبير من غير مراجعة.

## إضافة ميزة

الترتيب المتّبع: كلمة مفتاحية في `lexer/tokens.py` → عامل/أوّلية في `parser/precedence.py` → عقدة في `compiler/ast/nodes.py` → تنفيذ في `runtime/interpreter` (و`vm/` لو مدعومة) → اختبارات → توثيق. التفاصيل في `docs/development/guide.md`.

## أسلوب الكوميت

سطر أول موجز بصيغة الأمر، وبعده **ليه** التغيير اتعمل (مش إيه اللي اتغيّر بس). مثال:

```text
Reject negative and fractional repeat counts

Silently running zero iterations hid a typo, so كرر now reports E4004.
```

## الترخيص

المساهمة معناها موافقة على نشر العمل تحت رخصة MIT.

</div>
