# 貢獻指南

感謝協助改善 Codex／Claude／電池狀態小工具。請先建立議題描述問題或建議，再以小型、聚焦的
Pull Request 提交變更。

## 開發流程

1. Fork 專案並從主要分支建立功能分支。
2. 依 `README.md` 建立 `.venv` 及安裝鎖定依賴。
3. 每個行為變更都加入或更新自動測試。
4. 提交前執行：

```powershell
.\.venv\Scripts\python.exe -m ruff format .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
git diff --check
```

5. 使用簡潔的 Conventional Commit 主旨，例如 `feat: add usage color controls`。

## Pull Request 內容

- 說明問題及解法。
- 列出實際執行的驗證項目。
- UI 變更請附上截圖。
- 不要提交憑證、OAuth token、使用量快取、`.venv`、`build` 或 `dist`。

## 安全性

請勿在公開議題披露憑證或可利用的安全弱點；安全問題請依 `SECURITY.md` 處理。
