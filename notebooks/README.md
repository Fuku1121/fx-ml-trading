# Notebook案内

## 最新の入口（2026-09-09）

- `10_research_review.ipynb`：保存済みの最新比較を読む。再学習しない。
- `archive/27_hgb_reintegration.ipynb`：最新HGB比較の元コード。元セル56の失敗、57の再集約、58の評価を保管。
- [今回の11段階・元セル対応表](../docs/RESEARCH_20260909.md#原本への対応)：履歴17–27、元セル36–58。

全27段階の履歴は、原本の実行を監査済みの製品コードに置き換えたものではありません。
最新HGBを動かすには監査済みの元価格データと必要なNotebook変数が必要です。結果を読むだけなら上記の閲覧Notebookを使います。

## 前回までの入口

# Notebook guide

- **Current**: [09_confidence_nested.ipynb](09_confidence_nested.ipynb) — 15分足の年別Confidence検証。
- **Previous**: [08_trade_quality.ipynb](08_trade_quality.ipynb) — 5分足のQuality検証。
- **Archive**: archive/01〜16 — 探索・失敗・修正を残した研究履歴。セル間の依存やインストール操作を含むため、一括実行用ではありません。

最新添付の0〜15セルは以前のコードとハッシュが一致したため重複保存せず、出典台帳から既存の履歴へ参照しています。
36番の空セルを除く全36セルを追跡できます。コード中の個人フォルダ名は置換し、元と保存版のSHA-256を記録しました。
保存出力はresults/imported_20260907/。HTML・埋込画像・実行メタデータは取り除いています。
