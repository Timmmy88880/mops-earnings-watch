# 財報觀測｜台股 Q3 財報追蹤

公開站台（GitHub Pages）：<https://timmmy88880.github.io/mops-earnings-watch/>

追蹤 **2026 Q3** 財報／自結公告，資料來自[公開資訊觀測站](https://mopsov.twse.com.tw/mops/web/t05st01)。

## 自動更新

GitHub Actions 每週一 **07:15（Asia/Taipei）**（cron `15 23 * * 0`）向官方查詢並更新 `web/data/2026-q3.json`，成功後部署到 GitHub Pages。也可在 Actions 手動執行 **Update data and deploy Pages**。

本儲存庫為獨立可運行副本（含更新腳本與測試）；私人開發版見 `Timmmy88880/mops-earnings-tracker`（不互相推送）。

## 本機

Python 3.12+、Node.js 22+（無第三方套件）。

```sh
python3 -m http.server 8765 --directory web
python3 -m unittest discover -s tests -v
node --test tests/core.test.mjs
python3 scripts/update_data.py --validate-only
python3 scripts/update_data.py
node scripts/build.mjs   # optional: copy web/ → dist/
```

## 資料口徑

「財報已公布」含公司公告與董事會通過財報；「自結數」含單季與前三季累計。詳見站內說明。季度設定在 `config.json`；換季時需同步調整資料檔與 `web/assets/app.js` 的載入路徑。
