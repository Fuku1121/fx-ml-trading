# コードの読み方

## 最新HGBコードを読む順序

まず [evaluation.py](../src/fx_research/hgb/evaluation.py) の `evaluate_year` を読むと、研究の手順を追えます。
過去で確率を補正し、前年で取引条件を選び、その条件を固定して翌年を評価する処理です。

| ファイル | 担当すること | 主な関数 |
|---|---|---|
| [config.py](../src/fx_research/hgb/config.py) | モデル・コスト・比較候補を固定する | 定数一覧 |
| [features.py](../src/fx_research/hgb/features.py) | 価格から入力情報と将来の正解を作る | `make_all_features`, `prepare_dataset` |
| [calibration.py](../src/fx_research/hgb/calibration.py) | モデルを学習し、予測確率のずれを補正する | `expanding_oof`, `choose_calibration` |
| [trading.py](../src/fx_research/hgb/trading.py) | 取引の選別、量、コスト、成績を計算する | `select_trades`, `choose_sizing`, `stats_of_returns` |
| [evaluation.py](../src/fx_research/hgb/evaluation.py) | 年の境界を決め、翌年の評価までをつなぐ | `make_split`, `evaluate_year` |
| [runner.py](../src/fx_research/hgb/runner.py) | 指定CSVを読み、年別評価と結果保存を行う | `run`, `main` |

## 整理によって変えたこと

元Notebookのセル58から、21個の関数・クラスと設定を役割別に抽出しました。日本語の説明を加え、短い処理の不要な改行を整理しています。
設定と関数の計算内容は、元の構文木（AST）との比較テストで一致を確認します。
元コードは [履歴27](../notebooks/archive/27_hgb_reintegration.ipynb) に保存しています。

実行入口は新しく追加したものです。Notebook内の変数を自動探索せず、CSVを引数で指定します。
既存の入力検査で時刻・重複・価格の不整合を拒否し、新しいフォルダへ取引・設定・データのSHA-256を保存します。
入力を自動修復しないため、元Notebookで受理していたデータが検査で止まる場合があります。

`summary.csv` は指定した全評価年の集計です。元の開発期間表（2020–2025年）と同じ集計範囲とは限りません。
`CHAMPION` などの元の候補名は、保存結果との対応を維持するため残しています。

## 動作確認の範囲

[HGBのテスト](../tests/test_hgb.py)では、元の計算との一致、未来価格を変えた場合の特徴量、欠測・年境界、校正、非重複とコスト、人工データによる実行を確認します。
人工データのテスト成功は、実市場の収益性を証明するものではありません。実価格での再評価と、[監査項目](HGB_METHODOLOGY.md)への対応は今後の作業です。

## 以前の比較基準

- RFの年別Confidence検証：[confidence.py](../src/fx_research/confidence.py)、[方法](METHODOLOGY.md)。
- 5分足Quality検証：[pipeline.py](../src/fx_research/pipeline.py)、[旧ベースライン](QUALITY_BASELINE.md)。
- 試行錯誤の原本：[Notebook一覧](../notebooks/README.md)。

最新HGB、以前のRF、5分足Qualityは異なる実験です。コードと保存成績を取り違えないよう、入口を分けています。
