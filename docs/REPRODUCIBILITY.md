# 閲覧・再現手順

## 保存結果だけを読む

環境構築なしで、GitHubの [最新研究報告](RESEARCH_FX3.md)と [再評価のCSV](../results/published/clean_annual_saved.csv) を読めます。
Notebookで表示する場合は、Python3.11以上で、リポジトリ直下から実行します。

```bash
python -m venv .venv
```

Windows PowerShell：`.venv\Scripts\Activate.ps1`、macOS/Linux：`source .venv/bin/activate`。

```bash
python -m pip install -e ".[notebook]"
jupyter lab notebooks/11_forward_paper_review.ipynb
```

閲覧Notebookは保存された表と仕様を表示します。再学習、API接続、仮想売買は開始しません。

## リポジトリの動作確認

Notebookを使わず、参照コードのテストだけを行う場合は次で確認できます。

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

テスト対象は、原本との計算一致、特徴量の未来情報混入、時間境界、仮想データによる以前のHGB/RF処理、保存資料の整合性です。
添付にモデル等の実体がないため、300取引のフルリプレイをこのテストで再実行しているわけではありません。

## 最新の固定モデルを再現する前提

[固定仕様と必要ファイル](FROZEN_SYSTEM.md#再現のために必要なファイル)を確認します。元の年別CSV・正規履歴、実際のモデルと校正器、manifest、300取引の明細、必要なruntime状態が必要です。
説明用の `frozen_contract_saved.json` を実際のmanifestとして置き換えないでください。
モデル等を揃えたら、入力ハッシュと特徴順を照合し、過去のモデルによる再現と全履歴学習済みのモデルによる将来推論を区別します。
API認証情報は本人の環境で管理します。今回のGitHub整理では認証情報を保存したり、新しい接続や常駐処理を開始したりしていません。

## 以前の比較用CLI

以下は旧実験を再評価するための入口です。最新41特徴量モデルや仮想売買システムを起動するものではありません。
入力は、時差付き時刻を先頭列に持つ15分足CSV、小文字の `open,high,low,close` 列です。出力先には未使用のフォルダ名を指定します。

```bash
python -m fx_research.hgb.runner --csv data/raw/usdjpy_15m.csv --out results/runs/hgb-baseline-001
python -m fx_research.confidence --csv data/raw/usdjpy_15m.csv --out results/runs/rf-baseline-001
```

依存範囲は `pyproject.toml` に記載しています。`requirements-verified.txt` は以前の環境記録で、最新Notebookの学習環境を完全に固定したものではありません。
