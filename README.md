# youtube-channel-analysis

YouTubeチャンネルの成長要因を、公開データの定量分析と動画内容の定性分析で調べるための共通基盤

Claude Code を使用して構築・分析した

- 共通の作業方針：[AGENTS.md](AGENTS.md)
- 分析方法（標準工程・指標・分類・品質基準・変更履歴）：[methodology/](methodology/README.md)
- 調査一覧

| チャンネル | 状態 | 方法論 | 資料 |
|---|---|---|---|
| 海外Yパパ | 完了 | 1.0.0（1.1.0 で頑健性を確認） | [指示書](docs/overseas-y-papa-analysis.md) / [最終報告書](reports/overseas-y-papa/FINAL_REPORT.md) / [頑健性](reports/overseas-y-papa/robustness.md) / [レビュー](methodology/reviews/2026-10-21-overseas-y-papa.md) |
| リュウジのバズレシピ | 試験調査（直近30本） | 1.1.0 | [試験結果](methodology/reviews/2026-10-21-trial-ryuji-buzz-recipe.md) / [草稿](reports/ryuji-buzz-recipe/DRAFT_REPORT.md) |
| たくみっく | 完了（品質ゲート通過） | 1.3.0 | [指示書](docs/upunushi-ossan-analysis.md) / [最終報告書](reports/upunushi-ossan/FINAL_REPORT.md) / [仮説検証](reports/upunushi-ossan/hypotheses.md) / [レビュー](methodology/reviews/2026-10-21-upunushi-ossan.md) / [修正前の版](reports/upunushi-ossan/archive/FINAL_REPORT-20261020-incomplete.md) |

- 海外Yパパ v1.0 は 1.3.0 の品質ゲートでは incomplete（外部統計との照合なし、1章に確信度なし）。成果物は当時のまま保全している

## 新しいチャンネルの調査を始める

```sh
# 1. URLから識別・収集・検証・定量分析・標本選定まで（自動）
.venv/bin/python -m ycanalysis.research https://www.youtube.com/@handle
```

- 終了時に調査状態と「次の作業」を表示する。自動工程が成功しても、定量分析までの段階では完成ではない
- 2. 以降は AIエージェント（Claude Code・Codex）または人間が続ける：調査目的、外部統計の記録、テーマの盲検検証、代表動画の字幕・映像の確認、仮説の事前登録と標本外検証、比較、報告書（手順は [AGENTS.md](AGENTS.md) の「URLだけの依頼」）
- 3. `.venv/bin/python -m ycanalysis.analyze.finalize <slug>` が品質ゲート（[evaluation.md](methodology/evaluation.md) 4章）を通過したときだけ `FINAL_REPORT.md` を作る
- 状態と根拠は `reports/<slug>/research_status.json`。作業用の報告書は `DRAFT_REPORT.md`（自動処理は上書きしない）、自動集計は `AUTO_DRAFT.md`
- 同じチャンネルIDの設定があれば既存調査を更新し、過去の最終報告書は `archive/` に退避してから更新する
- 収集が途中で止まった場合は `ytdlp_meta <slug> videos --resume <raw のディレクトリ>` で再開できる（品質ゲートが概要ページの動画数と照合して検出する）
- 人の操作が必要になりやすいもの：統計サイト（ユーチュラ等）が自動取得を拒否する場合の現在値の確認と記録
- 既存の分析コードを書き換えずに、設定ファイル（`config/channels/<slug>.toml`）でチャンネル固有の値を調整する

## 構成

```text
config/channels/<slug>.toml     チャンネル設定（識別情報と、テーマ・フラグ・期間・定型句など固有の値）
config/channels/<slug>.peers.toml  比較チャンネル探索用の検索語
src/ycanalysis/
  init.py    新しいチャンネルの初期化
  research.py URLから調査を連続実行
  run.py     標準工程の一括実行
  annotate.py 盲検コーディング用シートと一致率
  collect/   収集（ネットワークにアクセスするのはここだけ）
  analyze/   前処理・集計・検定・頑健性チェック・草稿
  visualize/ グラフ・一覧画像
methodology/  分析方法の仕様・変更履歴・レビュー・回帰の基準値
templates/    チャンネル設定・調査指示書・報告書のひな形
data/<slug>/
  raw/          取得した元データ（タイムスタンプ付き、上書きしない）
  processed/    raw から再生成できる加工データ
  annotations/  手作業のコーディング結果（raw から再生成できない人間の判断）
reports/<slug>/ 報告書・グラフ・サムネイル一覧
docs/           調査指示書・コーディング基準・作業記録
tests/          分析処理の自動テスト
```

共通コードは `src/`、チャンネル固有のものは `config/`・`data/<slug>/`・`reports/<slug>/`・`docs/<slug>-*.md` に分ける

## セットアップ

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock   # 検証済みバージョン
.venv/bin/pip install -e .
```

- Python 3.12 で検証
- `ffmpeg` と `node` が必要（映像のカット検出と、yt-dlp の YouTube 署名処理に使う）
- YouTube Data API のキーは不要（後述）

## 実行手順

`<slug>` は `config/channels/<slug>.toml` のファイル名

### Phase 1 収集

```sh
# 全動画のメタデータ（1本ずつ2〜3秒間隔、351本で約70分）
.venv/bin/python -m ycanalysis.collect.ytdlp_meta <slug> videos
# 中断した場合は同じスナップショットに追記
.venv/bin/python -m ycanalysis.collect.ytdlp_meta <slug> videos --resume data/<slug>/raw/ytdlp_videos/<日時>

.venv/bin/python -m ycanalysis.collect.ytdlp_meta <slug> thumbnails   # サムネイル
.venv/bin/python -m ycanalysis.collect.channel_page <slug>            # 現在の登録者数・総再生数・開設日
.venv/bin/python -m ycanalysis.collect.wayback <slug>                 # 過去のチャンネルページ（Wayback Machine）
```

### Phase 2 定量分析

```sh
.venv/bin/python -m ycanalysis.analyze.build_dataset <slug>   # raw → processed/videos.csv など
.venv/bin/python -m ycanalysis.analyze.quant <slug>           # 集計表とグラフ（annotations/labels_manual.csv が必要）
.venv/bin/python -m ycanalysis.analyze.thumbs <slug>          # サムネイル特徴量と一覧画像
```

### Phase 3 内容分析

```sh
.venv/bin/python -m ycanalysis.analyze.select_sample <slug>          # 高・中・低 各12本を選定
.venv/bin/python -m ycanalysis.collect.ytdlp_meta <slug> subs -- ID ...       # 字幕
.venv/bin/python -m ycanalysis.collect.media_sample <slug> -- ID ...          # 360p で一時取得 → カット検出・フレーム抽出 → 映像は削除
.venv/bin/python -m ycanalysis.analyze.phase3 <slug> metrics              # 話速・定型句の位置・カット数
.venv/bin/python -m ycanalysis.analyze.phase3 <slug> dossier --vid=ID     # 目視用の字幕要約
.venv/bin/python -m ycanalysis.analyze.phase3 <slug> sheet --vid=ID       # 目視用のフレーム一覧
```

`-` で始まる動画IDがあるため、ID は `--` の後ろ、または `--vid=ID` の形で渡す

### Phase 4 比較

```sh
.venv/bin/python -m ycanalysis.collect.search_peers <slug>   # 検索結果から比較候補を集計
# 比較チャンネルごとに config/channels/<peer>.toml を作り、直近40本を収集
.venv/bin/python -m ycanalysis.collect.ytdlp_meta <peer> videos --limit 40
.venv/bin/python -m ycanalysis.collect.ytdlp_meta <peer> thumbnails
.venv/bin/python -m ycanalysis.collect.channel_page <peer>
.venv/bin/python -m ycanalysis.collect.wayback <peer> --monthly
.venv/bin/python -m ycanalysis.analyze.peers <slug> <peer> <peer> ...
```

### テスト・回帰確認

```sh
.venv/bin/pytest                                              # 単体テストと海外Yパパの回帰テスト
.venv/bin/python -m ycanalysis.analyze.baseline <slug> check  # 主要な数値を基準値と照合
.venv/bin/python -m ycanalysis.analyze.robustness <slug>      # 指標・分類方法を変えて結論を再確認
```

## 技術選定

| 用途 | 採用 | 理由 |
|---|---|---|
| 言語 | Python 3.12 | pandas・統計・画像処理の資産があり、`tomllib` が標準 |
| メタデータ収集 | yt-dlp | APIキーなしで、再生数・高評価数・コメント数・説明文・字幕・公開時刻を取得できる。YouTube Data API v3 は今回キーが用意されていなかった |
| 過去の登録者数 | Internet Archive Wayback Machine | 統計サイト（Social Blade・Yutura・vidIQ）はボット対策で取得できず、アーカイブもなかった。Wayback のチャンネルページ HTML に当時の登録者数・動画一覧の再生数が残っている |
| 集計 | pandas | 表形式の加工・集計 |
| 検定 | scipy・statsmodels | Mann-Whitney・Kruskal-Wallis・頑健標準誤差つき回帰 |
| 画像 | Pillow・ffmpeg | サムネイルの色特徴、一覧画像、シーン変化によるカット検出 |
| グラフ | matplotlib | Markdown 報告書に埋め込む静的PNG |

YouTube Data API v3 を使う場合の制約：公開後の日次再生数・視聴維持率・CTR・登録転換率は API でも取得できない（チャンネル所有者の YouTube Analytics のみ）。取得できる項目は yt-dlp と同等のため、今回は yt-dlp で代替した

## データの扱い

- `.env`・認証情報は Git 管理外
- 動画・音声ファイルは取得後に削除し、Git 管理外
- 字幕全文（`raw/subs/`）・サムネイル原画像（`raw/thumbnails/`）・映像フレーム（`raw/frames/`）は第三者の著作物のためローカル保持のみ
- Wayback のHTML（`raw/wayback/*.html`、計約160MB）は容量のため管理外。`cdx_*.json` の一覧から `collect.wayback` で同じスナップショットを再取得できる
- 別の環境で分析を再現するには、管理外のデータを Phase 1 のコマンドで再取得してから `analyze` を実行する
- `reports/<slug>/thumbnails/` には分析用の縮小一覧画像を置いている。リモートに公開する前に、引用の範囲として妥当か判断すること
- 依存ライブラリのバージョンは `requirements.lock` に固定
