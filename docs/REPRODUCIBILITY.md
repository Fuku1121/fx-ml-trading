# 実行方法と再現範囲

公開物で検査できる範囲の正本です。研究の採否・数値は [RESULTS](RESULTS.md) に集約しています。

## APIキーなしで検査する

リポジトリ直下で、研究コードはPython 3.11以上を使います。

```bash
python -m venv .venv
# Windows: .venv/Scripts/Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

paper tradingはPython 3.13の別環境を使います。

```bash
python -m pip install -r paper_trading/requirements.txt
python -m unittest discover -s paper_trading -p 'test_*.py' -v
python -m unittest discover -s research/multicurrency-20260917 -p 'test_*.py' -v
python -m unittest discover -s research/edge-search-20260917 -p 'test_*.py' -v
python paper_trading/demo.py
```

デモは人工価格とダミー判断です。実接続や収益性の検証ではありません。配布していない学習済みモデルを必要とする1件は明示的にskipします。GitHub Actionsにも研究用とpaper用の検査があります。

## 保存結果を見る

[CSVの分類](../results/README.md) と [Notebook案内](../notebooks/README.md) から読みます。閲覧Notebookは保存出力を表示するもので、同じ学習を再実行した証拠ではありません。Notebook環境が必要なら `python -m pip install -e ".[notebook]"` で追加します。

## 全実験を再現するには

元の年別CSV、正規履歴、学習済みモデル・校正器、実際のmanifestと特徴順、過去取引明細、必要なruntime状態が別途必要です。これらは公開していません。公開の説明用JSONやダミー推論で置き換えて、同じモデルを検証したとは扱えません。

[当時の固定仕様](archive/FROZEN_SYSTEM.md) と [照合記録](archive/VERIFICATION.md) は履歴です。今回のテストが300取引の全リプレイや全学習を再実行しているわけではありません。依存範囲は `pyproject.toml`、以前の環境記録は `requirements-verified.txt` にあり、全研究環境を完全固定したものではありません。

## 配備の扱い

`paper_trading/` は以前の4通貨比較を元にした参照コードです。モデル・認証情報・運転状態は同梱しません。元の `bundle_hashes.json` を保持しているため、変更後のコードをそのまま既存運転へ上書きできません。検査を無効化して起動しないでください。今回の整理はクラウドへ配備していません。

旧実験用CLIや当時の環境手順は [旧再現手順](archive/REPRODUCIBILITY_20260924.md) に保存しています。

## 2026-09-28の整理時の検査

Windows / Python 3.13で研究40件、paper trading 30件（29成功・非公開モデル1件skip）、他通貨5件、候補探索3件を確認しました。変更前後で研究・paperの既存テスト結果は同じです。合成デモとcompileallも成功しました。

さらに変更前commit `1b4dd94` のengineと変更後engineへ同じpaperテスト入力を与え、154箇所でメモリ状態、SQLiteの全5テーブルとschemaが完全一致することを確認しました。これは既存テストが通る経路の比較であり、すべての入力に対する証明ではありません。Markdownのローカルリンク・見出し参照と、履歴20文書の本文保持も確認しています。
