# {name} 成長要因調査 報告書（草稿）

- 対象：[{name}]({url})（`{channel_id}`）
- データ取得日：{retrieved}
- 方法論バージョン：{version}
- 表記：【事実】データで確認できたこと、【推論】データからの解釈、【仮説】公開データで検証しきれないもの
- 自動生成した事実の節と、人間の判断で書く節（「要記入」）がある。要記入の節は methodology/evaluation.md の基準で書く

---

## 1. 調査概要と主要な結論

（要記入：問い・結論の要約・再現可能性の表）

### 自動集計の要点

{summary}

## 2. チャンネルの成長過程

![登録者数の推移](charts/01_subscribers.png)
![月別投稿本数と再生数](charts/02_monthly.png)
![動画ごとの再生数](charts/03_views_timeline.png)

{growth}

## 3. テーマ・タイトル・サムネイルの分析

{themes}

![特徴の有無による差](charts/05_feature_effects.png)

（要記入：手作業コーディングの結果と反例。サムネイルは thumbnail_tables.md と一覧画像を確認する）

## 4. 動画尺・投稿戦略の分析

![尺](charts/06_duration.png)
![尺区分ごとの相対指数](charts/07_duration_rel.png)
![投稿](charts/08_posting.png)

{duration}

## 5. 動画構成・映像表現・ナレーションの分析

（要記入：processed/phase3_sample.csv の代表動画について、字幕と映像を確認した結果）

## 6. 類似チャンネルとの比較

（要記入：選定根拠と比較表。ycanalysis.analyze.peers の出力を使う）

## 7. 成長要因の仮説検証

（要記入：methodology/evaluation.md の仮説表の形式）

### 頑健性チェックの結果

{robustness}

## 8. 他チャンネルでも再現可能な制作手法

（要記入）

## 9. 分析の限界と未検証事項

{limits}
