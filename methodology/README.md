# 調査方法（標準手順）

分析方法の基準となる情報源。現在のバージョンは [CHANGELOG.md](CHANGELOG.md) の先頭、コードでは `ycanalysis.METHODOLOGY_VERSION`

| 文書 | 内容 |
|---|---|
| [metrics.md](metrics.md) | 指標の定義・計算方法・前処理 |
| [classification.md](classification.md) | 動画の分類基準、共通フラグと規則、コーディングと一致率の手順 |
| [evaluation.md](evaluation.md) | 品質基準、仮説の評価基準、改善サイクルの手順 |
| [CHANGELOG.md](CHANGELOG.md) | 方法論の変更履歴とバージョン |
| [reviews/](reviews/) | 調査ごとの方法論レビュー |
| [baselines/](baselines/) | 回帰テスト用の主要な数値 |

## 共通部分と個別部分

| 共通（`src/`・`methodology/`・`templates/`） | 個別（チャンネルごと） |
|---|---|
| データ取得・検証・前処理 | 対象チャンネルと調査目的（`docs/<slug>-analysis.md`） |
| 指標の計算（相対再生指数など） | テーマ体系・固有の特徴フラグ（`config/channels/<slug>.toml` の `[themes]`・`[flags]`、`docs/<slug>-codebook.md`） |
| 共通の特徴フラグと判定規則 | 手作業のラベル（`data/<slug>/annotations/`） |
| 比較・検定・頑健性チェック | 比較対象（`config/channels/<slug>.peers.toml` と比較チャンネルの設定） |
| 可視化・報告書の基本構成 | 個別の仮説・発見・結論（`reports/<slug>/`） |
| 品質基準・仮説の評価基準 | 定型句・シリーズ名・期間の区切り（設定ファイル） |

全チャンネルに同じテーマ体系や仮説を強制しない。共通工程を基本にし、設定とラベルで拡張する

## 標準工程

「自動」は `python -m ycanalysis.run <slug>` に含まれる。「人間の判断」は、AI エージェントが下案を作ってもよいが、判断の根拠を記録し、確信度の判定には人間の確認を入れる

| # | 工程 | 入力 | 処理 | 出力 | 完了条件 | 品質確認 | 区分 |
|---|---|---|---|---|---|---|---|
| 1 | 調査対象の特定 | チャンネルURL、調査目的 | `ycanalysis.init` で識別情報を取得、設定・ディレクトリ・指示書のひな形を作る | `config/channels/<slug>.toml`、`docs/<slug>-analysis.md` | 指示書に目的・範囲・人間の判断が必要な工程が書かれている | チャンネルIDがチャンネルページと一致する | 自動＋人間 |
| 2 | データ収集 | 設定 | 全動画メタデータ、サムネイル、概要ページ、Wayback | `data/<slug>/raw/`（タイムスタンプ付き、manifest.json） | 一覧の本数と取得本数の差が説明できる | 失敗した動画ID と理由がログにある | 自動 |
| 3 | データ検証・前処理 | raw | `analyze.build_dataset`：種別判定、指標の計算、Wayback の解析と異常値の検出 | `processed/videos.csv`、`channel_history.csv` | 重複0、欠損の件数と理由が `robustness.md` にある | 概要ページの動画数と取得本数の比較、異常値フラグの確認 | 自動 |
| 4 | 成長過程の分析 | processed | `analyze.quant` 1・2章：登録者・再生の推移、急増区間、期間区分 | `phase2_tables.md`、図01〜03 | 急増区間ごとに区間内の上位動画がある | 観測点の数と出典を報告書に書く | 自動 |
| 5 | テーマ・タイトル・サムネイル | processed、`annotations/labels_manual.csv` | テーマ別・特徴別の比較、重回帰、規則ベースのフラグ、サムネイル特徴量と一覧 | `phase2_tables.md` 3・4章、`thumbnail_tables.md`、図04・05 | 全動画にテーマがある、主要フラグの κ が算出されている | [classification.md](classification.md) の一致率、`analyze.robustness` | 人間（ラベル）＋自動 |
| 6 | 動画尺・投稿戦略 | processed | 尺区分・時間帯・曜日・同日投稿・シリーズ | `phase2_tables.md` 5・6章、図06〜08 | — | 交絡（期間・テーマ）を回帰で確認 | 自動 |
| 7 | 代表動画の選定 | `analysis_videos.csv` | `analyze.select_sample`：分位×期間×テーマの規則 | `processed/phase3_sample.csv` | 各群の本数が揃う、補充した場合は理由を記録 | 群・期間・テーマの偏りを表で確認 | 自動 |
| 8 | 動画内容の分析 | 選定動画 | 字幕・フレーム取得（`collect.media_sample`）、`analyze.phase3` の計測と目視コーディング | `annotations/phase3_coding.csv`、図11 | 全動画の字幕とフレームを確認した | 自動検出と手作業の判定の一致を確認 | 人間＋自動 |
| 9 | 類似チャンネルとの比較 | 検索語 | `collect.search_peers` で候補、選定、`analyze.peers` | `phase4_tables.md`、図09・10 | 選定根拠が書かれている | 比較条件（直近 N 本・公開 N 日以上）を揃える | 人間＋自動 |
| 10 | 成長要因の仮説検証 | 1〜9の結果 | 仮説ごとに支持・反証・代替説明・確信度・再現可能性 | 報告書7章 | 4段階（発見・クリック・継続・再訪）の各仮説に確信度がある | [evaluation.md](evaluation.md) の基準、頑健性チェック | 人間 |
| 11 | 最終報告書 | 全結果 | `analyze.draft_report` で草稿、人間が判断の節を書く | `reports/<slug>/FINAL_REPORT.md` | 9章構成、各結論に出典・URL・数値 | [evaluation.md](evaluation.md) の報告書チェックリスト | 人間＋自動 |
| 12 | 調査方法の振り返り | 報告書、ログ | 方法論レビュー、改善案の検証と採否 | `methodology/reviews/`、`CHANGELOG.md` | 改善案ごとに採用・保留・却下が決まっている | 回帰テスト、基準値の照合 | 人間＋自動 |

## 新しいチャンネルの調査

```sh
# 対象の特定から収集、暫定分類、分析、報告書、レビューまで
.venv/bin/python -m ycanalysis.research https://www.youtube.com/@handle

# 自動分類を検証または置き換える場合
.venv/bin/python -m ycanalysis.annotate <slug> export --columns theme,intl_compare,...
#    → classification.md の手順でテーマ体系を作り、data/<slug>/annotations/labels_manual.csv を作成
#    → config の [themes]・[flags]・exclude_themes を埋めて再実行
.venv/bin/python -m ycanalysis.run <slug>

# 8. 内容分析（人間の判断）
.venv/bin/python -m ycanalysis.collect.ytdlp_meta <slug> subs -- <ID...>
.venv/bin/python -m ycanalysis.collect.media_sample <slug> -- <ID...>
.venv/bin/python -m ycanalysis.analyze.phase3 <slug> metrics

# 9. 比較、10〜11. 仮説検証と報告書、12. レビュー
```

## 調査の品質を保つ順序

1. 再生数を見る前にテーマ体系と判定基準を決める（可能なら）
2. 再生数を伏せたシートで判定する
3. 結果を見てから基準を変えた場合は、その事実と理由を記録する
4. 結論を書く前に `analyze.robustness` を実行する
5. 自動テーマは暫定結果として `labels_auto.csv` に保存し、人手ラベルと混同しない
