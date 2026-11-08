<div dir="rtl">

# خطة العمل المتبقية — AlArabiya

> **آخر تحديث:** 2026-11-08 · **خط الأساس:** `bd0dcd8` · **البوابات الحالية:** 610 اختبار على Linux / 608 على Windows (+2 skip) · `ruff` نضيف · `mypy strict` على 46 ملف · CI أخضر على Ubuntu/Windows × 3.12/3.13/3.14.

البنود هنا هي **فقط** ما لم يُنفَّذ، أو نُفِّذ جزئيًا بحدود مكتوبة. كل بند مغلق لا يُعاد فتحه. الحالة التفصيلية في [`docs/current-feature-status.md`](docs/current-feature-status.md)، والدين في [`docs/technical-debt.md`](docs/technical-debt.md)، والمراحل في [`docs/arbic-2.0-roadmap.md`](docs/arbic-2.0-roadmap.md).

---

## 1. تم تثبيته (مرجع، لا يُعاد)

- المراحل 0–2: الأساس، CI، الدوال، القوائم/القواميس، الوحدات، `اكسر`/`كمل`.
- CLI: `run/check/repl/init/doctor/build/test/format/bench/lsp/debug`.
- مكتبة قياسية مرفقة: `نصوص`، `قوائم`، `رياضيات` (استيراد بالاسم + أولوية لملف المشروع).
- عزل: عملية عاملة منفصلة + حدود موارد + مهلة + سقف مخرجات + seccomp على Linux x86_64 (شبكة + كتابة).
- مصحّح DAP للمفسّر: نقاط توقف، `next/stepIn/stepOut`، مكدّس، نطاقات، متغيرات، مخرجات كأحداث `output`.
- مدير حزم محلي + lockfile + منع traversal/symlink escapes.

---

## 2. P0 — أمن قبل أي تنفيذ غير موثوق

- [ ] **TD-01 (تدوير الأسرار):** الملفات السبعة (`cmdkey_all.txt` وغيره) اتشالت من القرص ومش في التاريخ، لكن أي مفاتيح كانت فيها لازم تتلغى/تتدوّر من المالك. تأكيد: `git log --all -- '*.txt'` نظيف.
- [ ] **TD-20 (Windows/macOS):** AppContainer على Windows و`sandbox-exec` على macOS، + منع القراءة برّه مجلد المشروع، + قيود شبكة على غير Linux.
- [ ] **حماية فرع `main`:** إعداد GitHub يدوي (مراجعة مطلوبة + منع force-push + فحص CI إلزامي).
- [ ] **مراجعة `SECURITY.md`** بعد أي توسيع لحدود العزل أو قبل interop.

> لا يُبدأ interop/playground قبل إغلاق هذا القسم.

---

## 3. P1 — اللغة والأدوات

### Phase 3 — OOP والبرمجة التعبيرية

- [ ] `صنف` + `__تهيئة__` + خصائص + طرق + طرق ساكنة.
- [ ] وراثة (قرار موثّق: مفردة أم متعددة) + استدعاء الأساس.
- [ ] تغليف/خصوصية + interfaces أو protocols.
- [ ] lambda + دوال عالية الرتبة + decorators + generators + context managers + pattern matching تدريجيًا.
- [ ] دعم كامل: parser + AST + مفسّر + VM + فاحص أنواع + LSP + توثيق + أمثلة + اختبارات رجعية.
- [ ] ADR لدلالات الوراثة والتهيئة قبل الكود.

### Phase 4 — نظام الأنواع والتحليل الدلالي

- [ ] Symbol tables + module-aware analysis (التحليل الحالي ملف واحد).
- [ ] أنواع كاملة: `قائمة[T]`، `قاموس[K,V]`، `اختياري[T]`، union types، استدلال محلي.
- [ ] strict mode + قرار موثّق: هل يفرض `run` الأنواع أم يظل `check` وحده؟
- [ ] اختبار سلبي لكل عملية نوعية غير صالحة.

### Phase 9 — أدوات المطوّر (الناقص)

- [ ] **formatter كامل:** تخطيط وفواصل ومسافات حول العمليات، مع idempotency؛ الحالي مسافات فقط.
- [ ] **LSP:** `definition`، `references`، `rename`، `signatureHelp`، `codeAction` — الموجود حاليًا `hover`/`completion`/`documentSymbol` بس.
- [ ] **debugger:** دعم VM، نقاط شرطية/`hitCondition`/logpoints، `evaluate`، متغيرات قابلة للتوسيع، `terminate` أثناء التشغيل، تتبّع الوحدات المستوردة.
- [ ] **VS Code:** تسجيل لغة `arabic` وتلوين نحوي، تجربة الإضافة على المحرّر فعليًا، ثم النشر على السوق.

---

## 4. P2 — الأداء والتوسع

### Phase 5 — IR والمحسِّن

- [ ] ADR لاختيار التمثيل (SSA أم ثلاثي العناوين).
- [ ] AST→IR lowering + IR validator + مفسّر IR.
- [ ] constant folding + dead code elimination + constant propagation + CSE.
- [ ] اختبارات تفاضلية: مفسّر IR = المفسّر الشجري على كل الرجعية.
- [ ] كل تحسين له اختبار «قبل/بعد» + قياس قبل أي ادعاء سرعة.

### Phase 6 — VM وinterop

- [ ] صيغة bytecode مُصدَّرة (magic + version + checksum) وتحقق قبل التنفيذ.
- [ ] تعليمات ناقصة: استثناءات، وحدات، مجموعات + source maps/debug info.
- [ ] `--engine=interpreter|vm` + تصحيح على VM.
- [ ] Python interop: allowlist، تحويلات أنواع صريحة، أخطاء واضحة — **خلف العزل المكتمل**.

### Phase 7 — المكتبة القياسية

- [ ] `ملفات`، `وقت`، `عشوائي`، `JSON`، `نظام`، `أخطاء`، `اختبارات`.
- [ ] لكل وحدة: API عربي متسق + توثيق + أمثلة + اختبارات + تحقق مدخلات.
- [ ] الشبكة مؤجَّلة لحد إغلاق عزل P0.

### Phase 8 — الحزم

- [ ] checksums + lockfile موقّع + بصمات قبل أي حذف/نسخ.
- [ ] سياسة سكربتات تثبيت صريحة (رفض غير الموقّع/غير المصرّح).
- [ ] حدود archive bombs + حماية dependency confusion.
- [ ] `search`/`update`/`publish` + سجلّ شبكة (يحتاج استضافة وقرار مالك).

### Phase 10 — Playground والإصدار

- [ ] playground معزول بحدود موارد (بعد P0).
- [ ] توسيع fuzz/property/security suites (بلا Hypothesis، حتمية).
- [ ] benchmarks نهائية + تخزين تاريخي للأرقام.
- [ ] changelog + دليل ترحيل + إصدار (شروط ADR-01 قبل `1.0.0`).

---

## 5. ديون صغيرة/توثيق

- [ ] **TD-11:** توثيق `technical-debt.md` قديم — REPL بقى بيعدّ عمق الكتل والأقواس (`_pending_depth`)، مش `_bracket_delta`. تحديث الوصف وتصنيف المتبقي (إن وجد).
- [ ] **TD-13:** checksums وسكربتات التثبيت (تكرار مع Phase 8).
- [ ] **TD-14:** property tests وأنظمة ملفات غير مصرّح بها.
- [ ] **TD-15:** أرقام أداء تاريخية بدل لقطة واحدة.
- [ ] **TD-20:** تحديث الحدود بعد Windows/macOS.
- [ ] **TD-09:** strict/module-aware (تكرار مع Phase 4).
- [ ] مزامنة `docs/current-feature-status.md` بعد كل مرحلة.

---

## 6. بوابة إغلاق أي بند

- تنفيذ + اختبارات (وحدة + تكامل عند الحاجة + رجعية) + توثيق يصنّف الميزة + مثال يعمل + حدود مكتوبة.
- `python tools/check.py` + `check_links` + CI على المصفوفات الست قبل الدمج.
- لا ادعاء «شغّال» بدون تشغيل فعلي أو اختبار يثبته.
- أي كسر سلوكي: ADR + دليل ترحيل + اختبار توافق.

---

## 7. الترتيب المقترح

1. **Phase 3 (OOP)** — أكبر فجوة لغوية، وبتفتح lambda/generators.
2. **Phase 4 (الأنواع)** — تعتمد على OOP.
3. **Phase 5 (IR)** ثم **Phase 6 (VM/interop)** بعد إغلاق عزل P0.
4. **Phase 7 (stdlib)** و**Phase 8 (حزم)** بالتوازي مع الأدوات.
5. **Phase 9 (أدوات)** تدريجيًا، و**Phase 10** في الآخر.

</div>
