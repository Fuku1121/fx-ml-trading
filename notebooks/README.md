# Notebookと研究履歴の案内

最新の説明は [固定モデルと仮想売買の構成](../docs/FROZEN_SYSTEM.md) から読めます。
保存結果の閲覧入口は [11_forward_paper_review.ipynb](11_forward_paper_review.ipynb) です。学習やAPI接続は行いません。

| 履歴番号 | 内容 |
|---|---|
| 01–16 | 方向予測、Quality、年別Confidenceまで |
| 17–27 | 時間帯・校正・取引量・モデル・特徴量の比較 |
| 28–30 | 混在データの調査、年別CSV再構築、再評価 |
| 31–32 | 41特徴量のモデル固定、全履歴での計算一致 |
| 33–34 | 約定時刻・価格・費用と300取引の再現 |
| 35–36 | 仮想売買基盤、新しい確定足の入力、市場API接続 |

[追加分の元セル対応表](../docs/RESEARCH_FX3.md#出典とコードの案内) · [前回の対応表](../docs/RESEARCH_20260909.md#原本への対応)

archiveは研究原本です。Notebook変数や外部ファイルへの依存、失敗したコードも保存しており、一括実行する入口ではありません。
特に元セル82は構文エラーのまま履歴として保持し、その後のセル83に成功出力があります。
自動判定のPASSやREADYは保存時点の検査結果です。現在も接続中・稼働中であるという意味ではありません。

旧結果の閲覧は [10_research_review.ipynb](10_research_review.ipynb)、旧RFは [09_confidence_nested.ipynb](09_confidence_nested.ipynb) を参照してください。
旧HGB結果は混在データを含む履歴として扱います。最新の特徴定義は `src/fx_research/frozen/`、以前の30/50比較は `src/fx_research/hgb/` です。
