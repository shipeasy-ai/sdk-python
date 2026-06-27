Labels render in the **browser**, via the Shipeasy client SDK's `t()` — the
Python server SDK has no render helper. Once the loader tag (see setup) is in
`<head>`, the client renders translated text:

```js
// browser (Shipeasy client SDK), profile {{PROFILE}}
t("checkout.cta");
```
