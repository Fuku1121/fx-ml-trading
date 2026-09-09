# コードの読み方

## 現在の入口

現在の候補は41特徴量の `BASE_PLUS_REGIME` です。[固定モデル・仮想売買の構成](FROZEN_SYSTEM.md)から、各段階の元コードへ進めます。

今回、純粋な特徴量計算を次の2ファイルへ抽出しました。原本の6関数と定数の計算内容・特徴順を一致テストで確認しています。

| ファイル | 内容 |
|---|---|
| [frozen/base_features.py](../src/fx_research/frozen/base_features.py) | セル66の基本30特徴量。価格変化、変動性、移動平均、ローソク足など |
| [frozen/features.py](../src/fx_research/frozen/features.py) | セル67の相場状態の追加特徴。41特徴量の順序は `FEATURE_SETS["BASE_PLUS_REGIME"]` |
| [test_frozen_features.py](../tests/test_frozen_features.py) | 原本一致、未来データの影響、全履歴の接頭部分、取り込み資料の整合性 |

`make_final_tournament_features` に正規の全価格履歴を渡して計算します。この関数は学習やAPI接続を行いません。
返される表には比較候補の他の特徴もあるため、固定モデルへ渡す列は上記41特徴量の順に限定する必要があります。
直近250本などへ履歴を切り詰める変更は、元研究で見つかった符号特徴の不一致を再発させる可能性があります。

## 実行状態を扱うコード

モデル固定、推論エンジン、仮想売買、データ受信は [履歴31–36の案内](FROZEN_SYSTEM.md#説明とコードを対応させる) にまとめています。
これらはNotebook変数・モデルファイル・runtime状態に依存する原本です。必要な実体が添付されていないため、今回の整理では起動していません。
エラーになった試行も残し、その後の修正と保存結果を追えるようにしています。

## 以前の比較用コード

| 場所 | 対応する実験 |
|---|---|
| [hgb/evaluation.py](../src/fx_research/hgb/evaluation.py) | セル58の旧30/50特徴量比較。固定済み41特徴量とは別 |
| [confidence.py](../src/fx_research/confidence.py) | 以前のRF年別Confidence比較 |
| [pipeline.py](../src/fx_research/pipeline.py) | 5分足Quality比較 |

各参照実装のテスト成功は、そのモデルの保存成績や将来収益の保証ではありません。
旧HGBの高い成績は、その後のデータ混在調査によって現在の性能根拠から外しています。
