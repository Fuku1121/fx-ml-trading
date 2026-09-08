# 閲覧・実行手順

## 保存結果だけを読む

GitHubの [研究報告](RESEARCH_20260909.md) と [年別CSV](../results/published/hgb_annual_saved.csv) は、環境構築なしで読めます。
Notebookで表を表示したい場合は、下記の環境を作り、リポジトリ直下で実行します。

```bash
python -m pip install -e ".[notebook]"
jupyter lab notebooks/10_research_review.ipynb
```

このNotebookは保存CSVを読みます。価格データ取得や再学習は行いません。

## Python環境を準備する

Python 3.11以上を使用します。コマンドはリポジトリ直下で実行してください。

```bash
python -m venv .venv
```

Windows PowerShellでは `.venv\Scripts\Activate.ps1`、macOS/Linuxでは `source .venv/bin/activate` で有効化します。

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

## 最新HGB参照実装を実行する

監査した15分足CSVを `data/raw/` に置きます。先頭列は時差付きの足開始時刻、価格列は小文字の `open,high,low,close` です。
次は形式を示す架空の例です。

```csv
timestamp,open,high,low,close
2020-01-06T00:00:00+00:00,150.0,150.1,149.9,150.02
2020-01-06T00:15:00+00:00,150.02,150.1,149.95,150.03
```

```bash
python -m fx_research.hgb.runner --csv data/raw/usdjpy_15m.csv --out results/runs/hgb-001
```

この入口は時刻・重複・不正な価格を検査し、自動の再集約は行いません。既存の出力フォルダには上書きしません。
元セル58の2020–2026年の比較を行うため、それ以前の十分な学習期間が必要です。データ不足の年は理由を記録してスキップします。
短い架空CSVで実価格の成績を確認することはできません。

| 出力 | 内容 |
|---|---|
| `run.json` | 入力期間、設定、依存バージョン、入力・ソースSHA-256、実行状態 |
| `annual.csv` | 年ごとの校正・閾値・時間帯・取引量方針と成績 |
| `trades.csv` | 取引の時刻・方向・価格・取引量・純損益 |
| `period_status.csv` | 年と候補ごとの評価／データ不足の状態 |
| `summary.csv` | 指定した全評価年を統合した候補別の成績 |

損益と割合は小数単位です。例えば `0.00004 = 0.004%`。`win_rate` は純利益が出た取引の割合です。
`summary.csv` は2026途中も含み得るため、2020–2025年だけの保存表と直接比較しないでください。
HGBの年別計算は元実験を保持していますが、入力検査と保存処理は新規です。独立した実価格再実行はまだ行っていません。

## 以前のRF比較基準を実行する

```bash
python -m fx_research.confidence --csv data/raw/usdjpy_15m.csv --out results/runs/rf-001
```

こちらは校正・時間帯・取引量選択を含まない以前の比較基準です。[方法](METHODOLOGY.md)を参照してください。
依存関係の対応範囲は `pyproject.toml` に記載しています。`requirements-verified.txt` は以前の環境記録で、最新Notebookの完全な環境固定ファイルではありません。
