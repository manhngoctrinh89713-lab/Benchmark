# Halcyon API guide 2026
Pagination errors now use a top-level `errors` array. Each item carries `code` and `message`; the old `error.envelope` shape is deprecated and may be removed. Example:

```json
{"errors":[{"code":"cursor_expired","message":"The pagination cursor has expired."}]}
```
