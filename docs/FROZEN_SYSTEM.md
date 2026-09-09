# 固定モデルと仮想売買の構成

現在の候補は `BASE_PLUS_REGIME`、41特徴量です。以前の `hgb/` はセル58の30/50特徴量の参照実装で、固定モデルを起動するものではありません。

## 説明とコードを対応させる

| 処理 | 読む場所 | 必要なもの |
|---|---|---|
| 元の30特徴量 | [frozen/base_features.py](../src/fx_research/frozen/base_features.py) | 正規の価格履歴 |
| 41特徴量の定義と計算 | [frozen/features.py](../src/fx_research/frozen/features.py) | 全履歴。`FEATURE_SETS["BASE_PLUS_REGIME"]` の順序を維持 |
| データの再構築・比較 | [履歴29](../notebooks/archive/29_clean_dataset_rebuild.ipynb)、[履歴30](../notebooks/archive/30_clean_feature_tournament.ipynb) | 年別元CSV |
| モデル固定・推論 | [履歴31](../notebooks/archive/31_champion_freeze.ipynb)、[履歴32](../notebooks/archive/32_history_prefix_parity.ipynb) | モデル・校正器・manifest・正規履歴 |
| 時刻・価格・コストの照合 | [履歴33](../notebooks/archive/33_paper_price_semantics.ipynb)、[履歴34](../notebooks/archive/34_paper_cost_replay.ipynb) | 過去取引と正規価格履歴 |
| 新しいデータを処理する | [履歴35](../notebooks/archive/35_forward_paper_runner.ipynb)、[履歴36](../notebooks/archive/36_market_data_connection.ipynb) | runtime状態・入力足・本人のAPI設定 |

## 保存出力に記録された固定仕様

| 項目 | 設定 |
|---|---|
| バージョン | champion_v1_base_plus_regime_20260909 |
| 特徴量 | BASE_PLUS_REGIME、41個 |
| 確率校正 | ISOTONIC |
| 取引閾値・時間帯 | 0.58、ALL |
| 取引量 | STRONG、補正係数1.7451299836342953 |
| 保有 | 30分、重複保有禁止 |
| 費用 | 元本1倍あたり0.00004、取引量を掛ける前に控除 |
| 正規履歴 | 265,905行。任意のtail(N)に短縮しない |
| 最新接続状態 | 次の確定足を待機、処理0件、実注文なし |

[固定仕様の転記JSON](../results/published/frozen_contract_saved.json)は説明用であり、実際のモデルmanifestの代わりに読み込むファイルではありません。
元データのハッシュも保存出力からの転記です。この更新で元CSVの実体との一致を検証したわけではありません。

## 再現のために必要なファイル

Notebookには保存先の記録がありますが、学習済み `.joblib`、実際の `champion_manifest.json`、正規履歴CSV、300件の取引明細、runtime状態の実体は今回の添付には含まれていません。
そのためGitHub整理では、特徴量の参照コードと保存出力の照合を行い、300取引のフルリプレイや実市場API接続を新たに開始していません。
必要なファイルを揃えたうえで、環境・入力ハッシュ・固定仕様を照合することが再実行の前提です。

認証情報は環境変数などで本人の環境に設定します。学習済みモデル、APIキー、稼働中の状態や入力価格をGitへ追加しない構成にしています。
今回抽出した特徴量コードは読み込みだけでは学習・接続・取引を行いません。
