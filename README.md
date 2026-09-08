# USD/JPY Machine Learning Research

**機械学習でUSD/JPYの値動きを予測し、「どの取引を選び、どれだけ取引するか」を時系列データで検証する研究プロジェクトです。**

Python · pandas · scikit-learn · Time-series validation · Backtesting

[今回の研究報告](docs/RESEARCH_20260909.md) · [最新手法と監査](docs/HGB_METHODOLOGY.md) · [実験履歴](notebooks/README.md) · [実行・閲覧方法](docs/REPRODUCIBILITY.md)

## 30秒で分かるこの研究

- **問い**：予測精度のわずかな差を、コストを引いた後の取引の優位性につなげられるか。
- **方法**：過去データで方向を学習し、前年の検証データで確率校正・取引する時間帯・取引量を決め、翌年で評価する。
- **今回分かったこと**：特徴量を30から50へ増やしても、最新比較ではBASEの損益指標を上回らなかった。複雑にする前に、データ品質と極端に良い年の取引を監査する。
- **現在地**：HGBを用いたNotebook研究と検証履歴の整理まで。高PFの監査・未使用期間での評価・ペーパートレードは今後の課題。

## 工夫した点と技術

| 工夫 | コードで扱っている内容 |
|---|---|
| 未来の情報を使わない検証 | 年ごとの学習・Validation・Test、ラベルが判明する時刻での境界処理 |
| 精度だけで判断しない | 取引コスト、取引数、PF、最大ドローダウン、年別の安定性 |
| 要素ごとの効果を分ける | 時間帯・決済・確率校正・取引量・モデル・特徴量を段階的に比較 |
| 研究の判断を追跡できる | 採用保留・エラーも含む27段階の履歴、保存出力、原本のSHA-256 |

## 最新の研究フロー

```mermaid
flowchart LR
    A[USD/JPY 15分足] --> B[過去の値動きから特徴量]
    B --> C[HGBで上昇確率を予測]
    C --> D[確率の校正]
    D --> E[閾値と時間帯で取引を選別]
    E --> F[取引量を決める]
    F --> G[30分後に決済・コスト控除]
```

HGBは複数の決定木を順に学習する勾配ブースティングモデルです。最新比較は**BASE 30特徴量**と、変動性・相場状態を追加した**50特徴量**です。
コード中の `CHAMPION` は50特徴量候補の名前であり、比較に勝ったことを意味しません。

## 最新の保存結果：特徴量追加は改善につながったか

**出典は `FX (2).ipynb` セルindex 58の保存出力です。今回の整理で独立に再実行した成績ではなく、データ品質・損益集中の監査も未完了です。**

| 開発評価期間 2020–2025 | BASE・30特徴量 | 拡張候補・50特徴量 |
|---|---:|---:|
| 取引数 | 1,565 | 1,322 |
| 平均純損益 / 取引 | +0.0357% | +0.0216% |
| PF（利益合計÷損失合計） | 2.950 | 2.017 |
| 最大ドローダウン（決済ベース） | −2.17% | −1.95% |
| 2倍コストでのPF | 2.573 | 1.764 |

![Saved HGB comparison with annual diagnostic](results/figures/hgb_comparison_saved.svg)

追加候補はDDが小さい一方、平均純損益・PFでBASEを上回りません。2026途中のPFはBASE 2.322、追加候補2.034です。
BASEの2022年PF 10.463、2025年PF 15.197は特に監査が必要です。2026は研究中に繰り返し見ているため、独立した最終Holdoutとは扱いません。

[年別結果と解釈](docs/RESEARCH_20260909.md) · [年別CSV](results/published/hgb_annual_saved.csv) · [元の保存出力](results/imported_20260909/cell_58.txt)

## ここまでの試行錯誤

| 段階 | 結果からの判断 |
|---|---|
| Direction → MOVE / Quality → 年別Confidence | 方向精度だけでは不足。取引選別とコストを重視 |
| Session / TP・SL / 保有時間 | 時間帯の選別を検証。決済は30分固定を比較基準として維持 |
| Calibration / Position Sizing | 確率の偏りと、単純な取引量増加による効果を分けて確認 |
| Risk Engine | 過去年による選択では追加改善なし。採用を見送り |
| RF / ExtraTrees / HGB / Logistic | HGBを次の比較候補へ。AUCと損益が一致しないことを確認 |
| Trend / Volatility / Regime → 再統合 | 探索時の改善が完全な処理でも再現するかを比較。最新ではBASEを超えず |

[今回の詳しい経緯](docs/RESEARCH_20260909.md) · [以前の研究](docs/RESEARCH.md)

## 読む・実行する

| 目的 | 入口 |
|---|---|
| 最新研究を読む | [研究報告](docs/RESEARCH_20260909.md)と[方法・監査](docs/HGB_METHODOLOGY.md) |
| 最新のコードを読む | [履歴27：再集約とHGB比較](notebooks/archive/27_hgb_reintegration.ipynb)。元のデータとNotebook変数に依存 |
| 保存結果をNotebookで見る | [10_research_review.ipynb](notebooks/10_research_review.ipynb)。価格データや再学習は不要 |
| テスト済みのRF比較基準を実行 | `src/fx_research/confidence.py`。[再現手順](docs/REPRODUCIBILITY.md)を参照 |
| 過去のコードを追う | [27段階のNotebook案内](notebooks/README.md) |

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

既存の30件のテストはRFパッケージ等の計算・境界・人工データでの動作を検証します。最新HGBプロトタイプ全体の検証ではありません。
実価格データ・認証情報・他の会話履歴は同梱しません。

## 次の検証

1. 15分足の再集約と、2022・2025年の高利益取引を監査する。
2. 同一データ・同一処理でBASE / +VOL / +REGIME / +VOL+REGIMEを比較する。
3. 仕様を固定し、未使用期間で評価したうえでペーパートレード環境を構築する。

現在は一定コストによる研究用バックテストです。実際のbid/ask約定、注文送信、障害復旧まで検証したシステムではありません。
