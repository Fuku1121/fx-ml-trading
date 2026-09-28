# 研究履歴と情報源の分類

ここは当時の報告を保存する場所です。**historical / superseded — not current performance evidence**。数値や失敗記録は残し、冒頭の位置付けと移動後のリンクだけを補いました。現在の判断は [RESULTS](../RESULTS.md) を正本とします。

## 変更前の調査で分けたもの

| 分類 | 保存先 | 現在の扱い |
|---|---|---|
| 正規データ再構築・41特徴量選択・計算照合 | [RESEARCH_FX3](RESEARCH_FX3.md)、[FROZEN_SYSTEM](FROZEN_SYSTEM.md)、`results/published/clean_*` | 固定候補の根拠。保存結果であり、今回の再学習ではない |
| 5分足Quality・RF Confidence | [AUDIT](AUDIT.md)、[QUALITY_BASELINE](QUALITY_BASELINE.md)、[CONFIDENCE_BASELINE](CONFIDENCE_BASELINE.md)、[CONFIDENCE_AUDIT](CONFIDENCE_AUDIT.md)、[RF_METHODOLOGY](RF_METHODOLOGY.md)、[RESEARCH](RESEARCH.md) | 以前の比較基準。現在のモデル性能ではない |
| 混在データのHGB比較 | [RESEARCH_20260909](RESEARCH_20260909.md)、[HGB_METHODOLOGY](HGB_METHODOLOGY.md)、`results/published/hgb_*` | 高成績を現在の性能根拠から除外 |
| 当時の構成・説明の重複 | [OVERVIEW](OVERVIEW.md)、[CODE_GUIDE](CODE_GUIDE.md)、[旧再現手順](REPRODUCIBILITY_20260924.md)、[旧レビューガイド](REVIEW_GUIDE_20260924.md) | 現行4文書へ役割を集約。元の説明は履歴保存 |
| 過去のテスト実行記録 | [VERIFICATION](VERIFICATION.md)、[VERIFICATION_20260917](VERIFICATION_20260917.md) | 記載commit・環境での結果。現在のテスト数とは区別 |
| 旧クラウド比較 | [CLOUD_PAPER_20260917](CLOUD_PAPER_20260917.md) | 4通貨入力・2モデル比較の配置記録。現在のドル円単独運転ではない |
| 初期の作業背景・設定案内 | [PROJECT_CONTEXT.original](PROJECT_CONTEXT.original.md)、[旧PROJECT_CONTEXT](PROJECT_CONTEXT_20260909.md)、[GITHUB_SETUP](GITHUB_SETUP.md) | 歴史的な背景。現行の手順・公開設定の正本ではない |
| 9月12〜17日の追加研究 | [researchの索引](../../research/README.md) | 不採用候補も保存。コードが相互参照するためフォルダを移動しない |
| 原本セル・保存ログ・出典ハッシュ | [Notebook案内](../../notebooks/README.md)、[結果ファイルの分類](../../results/README.md) | 内容・パスを維持。計算再現と収益性の証拠を区別 |

## 正式資料との関係

現在の概要は [README](../../README.md)、構成は [ARCHITECTURE](../ARCHITECTURE.md)、評価規則は [METHODOLOGY](../METHODOLOGY.md)、採否と結果は [RESULTS](../RESULTS.md)、実行範囲は [REPRODUCIBILITY](../REPRODUCIBILITY.md) に集約しています。履歴の「最新」を根拠にこれらを上書きしません。

旧Notebookの参照先を壊さないため、`docs/AUDIT.md` と `docs/CONFIDENCE_AUDIT.md` には移動案内だけを残しました。数値表、原本コード、元出力、provenance JSONの削除・改変はしていません。
