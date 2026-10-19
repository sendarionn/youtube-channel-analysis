# youtube-channel-analysis

YouTubeチャンネルの成長要因を、公開データの定量分析と動画内容の定性分析で調べるための共通基盤

Claude Code を使用して構築・分析した

- 共通原則：[AGENTS.md](AGENTS.md)
- 調査一覧
  - 海外Yパパ：[指示書](docs/overseas-y-papa-analysis.md) / [最終報告書](reports/overseas-y-papa/FINAL_REPORT.md) / [作業記録](docs/overseas-y-papa-progress.md)

## 構成

```text
config/channels/<slug>.toml     チャンネル設定（ID・ハンドル・表示言語）
config/channels/<slug>.peers.toml  比較チャンネル探索用の検索語
src/ycanalysis/
  collect/   収集（ネットワークにアクセスするのはここだけ）
  analyze/   集計・検定・Phase別の分析
  visualize/ グラフ・一覧画像
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

### テスト

```sh
.venv/bin/pytest
```

## 別のチャンネルを調べる場合

1. `config/channels/<新slug>.toml` を作る（`channel_id` はチャンネルページの URL などで確認）
2. Phase 1・2 のコマンドを `<新slug>` で実行する
3. テーマ分類は `data/<新slug>/annotations/labels_manual.csv` に手作業で作る（列は [コーディング基準](docs/overseas-y-papa-codebook.md) を参照し、テーマ体系はチャンネルに合わせて作り直す）
4. `docs/<新slug>-analysis.md` に調査要件を書く

チャンネル固有の定型句（Phase 3 の挨拶検出など）は `analyze/phase3.py` の `PATTERNS` を書き換える

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
