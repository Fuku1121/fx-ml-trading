# 最新研究の閲覧（2026-09-09）

最新HGBコードは [履歴27](../notebooks/archive/27_hgb_reintegration.ipynb) にあります。元セル58は `bars` 変数に依存します。セル57の自動再集約を正しい価格データの保証とはみなしません。

保存結果だけを見る場合は `python -m pip install -e ".[notebook]"` の後、`jupyter lab notebooks/10_research_review.ipynb` を実行します。以下のCLI手順は以前のRF比較基準用で、最新HGBを実行するものではありません。

# 再現手順

## 1. 環境

Python 3.11以上。リポジトリ直下で:

```bash
python -m venv .venv
```

Windows PowerShell: `.venv\Scripts\Activate.ps1`

macOS/Linux: `source .venv/bin/activate`

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

依存範囲はpyproject.toml。requirements-verified.txtは以前のローカル検証時の記録であり、新Notebookの実験環境のロックではありません。

## 2. 固定CSVを用意

`data/raw/usdjpy_15m_2016_2026.csv` に元のDukascopy CSVを置きます。
先頭列はUTC offset付きの足開始時刻、価格列は `open,high,low,close`（小文字）。volumeは不要です。
以下は形式だけを示す架空の例です。

```csv
timestamp,open,high,low,close
2020-01-06T00:00:00+00:00,150.0,150.1,149.9,150.02
2020-01-06T00:15:00+00:00,150.02,150.1,149.95,150.03
```

元の取得スクリプトは [取得履歴](../notebooks/archive/12_long_history_data.ipynb) に保存しています。
パッケージの入れ直しなどのトラブルシュートも含むため、上から一括実行する入口ではありません。
データ取得元の利用条件、取得日時、BID系列であること、取得範囲を記録し、生データはGitへ追加しません。

## 3. 最新の修正済み実験

```bash
python -m fx_research.confidence --csv data/raw/usdjpy_15m_2016_2026.csv --out results/runs/confidence-001
```

出力先は新しいフォルダ名にします。最低3学習年＋前年Validationを必要とするため、短期間だけのCSVでは評価年が作れません。
フルの学習時間はCPUとデータ量に依存します。CIは人工データと小さい森で動作を確認し、投資成績を評価するものではありません。

Notebookの場合:

```bash
python -m pip install -e ".[notebook]"
jupyter lab notebooks/09_confidence_nested.ipynb
```

## 4. 結果を読む

| ファイル | 内容 |
|---|---|
| run.json | 入力期間・SHA-256・設定・環境・ソースSHA-256・完了状態 |
| annual.csv | 年ごとの状態、閾値、Test AUC、方向的中率、純利益率、PF、DD |
| validation_search.csv | 不採用・最低件数未達も含む閾値候補と選択スコア |
| trades.csv | シグナル・エントリー・決済時刻、方向、価格、予測スコア、純損益 |
| summary.csv | 全体・BUY・SELLの成績 |

損益と割合は小数単位。`0.00004 = 0.004%`。年別Testを見て再調整した場合、そのTestを未使用の最終評価とは呼べません。
元データの再取得は修正前成績の完全再現にはなりません。価格CSV・設定・環境・ソースを固定して比較してください。
