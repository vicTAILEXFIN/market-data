# 每日金融市場摘要：範本程式

- `digest_template.py`：data.json → email.html／email.txt，並執行格式與算術檢查（CHECKS: PASS 才可寄送）。
- `pick_closes.py`：Firecrawl 備援時，從 30 分K取結算參考價。

雲端排程每次從全新環境開始，執行時使用的是排程指示中內嵌的同一版本；這裡的檔案是版本紀錄與規格附錄（Notion PRD 連結至此）。修改時兩邊要一起更新。
