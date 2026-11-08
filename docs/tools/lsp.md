<div dir="rtl">

# أدوات المحرّر — خادم اللغة (LSP)

AlArabiya فيها **Language Server** مكتوب من الصفر (بدون أي اعتماديات)، بيتكلم
بروتوكول LSP عبر stdio، وبيعيد استخدام نفس الـ lexer/parser والفاحص النوعي.

## التشغيل

```bash
arabic lsp        # أو:  arabic-lsp
```

الخادم بيستنى رسائل JSON-RPC على stdin ويرد على stdout (مش للاستخدام اليدوي؛
المحرّر هو اللي بيكلّمه).

## القدرات

| القدرة | الوصف |
|---|---|
| تشخيصات مباشرة | أخطاء نحوية + فحص أنواع ثابت، بتتحدّث مع كل تعديل |
| `hover` | شرح الكلمات المفتاحية والدوال المدمجة تحت المؤشر |
| `completion` | إكمال: الكلمات المفتاحية + الدوال المدمجة + أسماء الأنواع |
| `documentSymbol` | قايمة الدوال والمتغيّرات في الملف |

التشخيصات بتستخدم نفس أكواد الأخطاء (`E1xxx`–`E5xxx`) مع الاقتراحات.

## الربط مع VS Code (مثال مختصر)

أي امتداد عميل LSP بسيط ينفع. مثال إعداد العميل (TypeScript):

```ts
import { LanguageClient, TransportKind } from "vscode-languageclient/node";

const client = new LanguageClient(
  "alarabiya",
  "AlArabiya",
  { command: "arabic", args: ["lsp"], transport: TransportKind.stdio },
  { documentSelector: [{ scheme: "file", language: "alarabiya" }] },
);
client.start();
```

وتعرّف نوع ملفات `.arb` كلغة `alarabiya` في `package.json` بتاع الامتداد.

## ملاحظة

الخادم بسيط بغرض التعليم: مزامنة المستند **كاملة** (full sync)، والإكمال
ثابت (مش حسب السياق). التوسّعات زي "اذهب للتعريف" و"إعادة التسمية" مراحل جاية.

</div>
