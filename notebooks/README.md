# Notebookと研究履歴の案内

## 最初に読むもの

| 目的 | 入口 |
|---|---|
| 最新の処理をPythonコードで読む | [HGB年別評価](../src/fx_research/hgb/evaluation.py)と[コード解説](../docs/CODE_GUIDE.md) |
| 最新の保存結果を表示する | [10_research_review.ipynb](10_research_review.ipynb)。モデルを再学習しない閲覧用 |
| RFの比較基準を実行する | [09_confidence_nested.ipynb](09_confidence_nested.ipynb) |
| 以前のQuality検証を実行する | [08_trade_quality.ipynb](08_trade_quality.ipynb) |

## 全27段階の研究履歴

`archive/` は試行錯誤を記録した原本の保管場所です。元のNotebook変数やデータに依存するコード、エラーになったコードも含みます。
一括実行する入口ではありません。新しい実行入口は [再現手順](../docs/REPRODUCIBILITY.md) を参照してください。

| 段階 | 内容 |
|---|---|
| 01–07 | データ取得、方向予測、取引選別、Qualityモデル |
| 08–16 | Quality再検証、取引量、予測期間、長期データ、年別Confidence |
| 17–18 | 年境界の修正、市場状態、取引する時間帯 |
| 19–21 | 決済方法、確率校正、取引量と配分 |
| 22–24 | リスク制御、モデル比較、HGB統合 |
| 25–27 | 特徴量比較、時間足再集約、最新HGB比較 |

[前半の研究報告](../docs/RESEARCH.md) · [後半の原本セル対応表](../docs/RESEARCH_20260909.md#原本への対応)

出典とコードのSHA-256は、[前回の記録](../results/imported_20260907/provenance.json)と[追加分の記録](../results/imported_20260909/provenance.json)にあります。
今回の添付のセル0–35は前回と同一、36–58が追加、59は空です。個人フォルダ名・実行メタデータを除いた原本を保持しています。
