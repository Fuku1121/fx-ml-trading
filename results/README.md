# 結果ファイルの分類

採否・現在の位置付けの正本は [RESULTS](../docs/RESULTS.md) です。ファイル名にpublishedがあっても、すべてが現在の性能根拠という意味ではありません。

| 保存先 | 扱い |
|---|---|
| `published/clean_*` | 再構築後のNotebook保存出力。現在の固定候補を選んだ根拠 |
| `published/frozen_contract_saved.json` | 固定仕様の説明用。配備manifestではない |
| `published/hgb_*`、`published/nested_*` | historical / superseded / not current performance evidence。旧比較の保存結果 |
| その他の旧import・legacy資料 | 過去研究と原本照合のために保存。現在の成績に合算しない |
| [forward/20260928_status.json](forward/20260928_status.json) | 日時付きの途中状態。全取引DBではない |

元のCSV・JSONの値とパスは保持しています。出典は [研究履歴](../docs/archive/README.md) から追えます。
