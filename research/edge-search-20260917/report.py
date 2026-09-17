from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
POLICY={'probability':'確率58%以上','cost_filtered':'確率＋予想値幅','expected_return':'予想値幅のみ'}


def main():
    results=pd.read_csv(ROOT/'results.csv');test=results[results.period=='test']
    assert len(test)==144
    selection=json.loads((ROOT/'frozen_candidates.json').read_text())
    watch=json.loads((ROOT/'watchlist_frozen.json').read_text())
    fresh=json.loads((ROOT/'additional_period_results.json').read_text())
    checks=json.loads((ROOT/'verification.json').read_text())
    assert checks['trade_summaries_checked']==288
    lines=['# コストと複数通貨情報を使った追加検証', '',
        '2026年9月17日。稼働中Notebook・仮想口座・実注文は変更していません。', '',
        '**過去の両期間で利益が残る研究案は見つかりましたが、採用条件を満たす案は0件です。** 少ない取引の偶然を利益の再現性と取り違えないため、採用見送りと追加確認を分けています。', '',
        f'72通りを2025年と2026年1〜8月に評価した144件のうち、通常コストでプラスは{int((test.return_pct>0).sum())}件。前回の32条件も失敗を含めて別フォルダに保存しています。', '',
        '## 何を変えたか', '',
        '- 予測時間を60・120・240分にしました。',
        '- 既存41特徴量に、他の3通貨の直近1・4・16本のリターンを加えた50特徴量も比較しました。',
        '- 上昇確率を予測するHGBに加え、ATRで正規化した値幅を予測するHGB回帰を学習しました。',
        '- 確率58%以上、確率58%以上かつ予想値幅が推定コストの1.5倍超、予想値幅のみ、という3方式です。最後の方式は確率58%を意味せず、別の売買判断です。',
        '- 市場が閉まっている週末と観測欠損を区別。週末に架空の足を追加せず、平日の欠損では150本の準備をやり直します。',
        '- NY17時の営業日境界をまたぐ保有を除外し、スワップの影響を避けた比較にしました。', '',
        '## 利益が残ったが取引件数が不足している案', '',
        '事前の採用条件は、2025年・2026年のそれぞれで30取引以上、通常コストと厳しいコストの両方でプラス。30件は最低限の調査条件で、統計的な十分性を保証する値ではありません。条件は変更せず、frozen_candidates.jsonの採用候補は空のままです。',
        'そのうえで、両期間で厳しいコストでもプラスになった少数取引の案を別の研究用watchlistとして固定し、9月分で一度だけ追加確認しました。これは採用条件を緩めたものではありません。', '',
        '| 通貨・方式 | 期間 | 取引数 | 回/日 | 期間収益 | 厳しいコスト |',
        '|---|---|---:|---:|---:|---:|']
    for c in watch['candidates']:
        for r in c['historical']:
            title=f"{c['pair']}・{c['horizon_minutes']}分・他通貨特徴量・{POLICY[c['policy']]}"
            lines.append(f"| {title} | {r['year']} | {r['trades']} | {r['trades_per_day']:.2f} | {r['return_pct']:+.2f}% | {r['stress_return_pct']:+.2f}% |")
    for r in fresh:
        lines.append(f"| {r['name']} | 2026年9月1〜15日 | {r['trades']} | {r['trades_per_day']:.2f} | {r['return_pct']:+.2f}% | {r['stress_return_pct']:+.2f}% |")
    lines += ['', '収益率は固定1倍相当で、年率ではありません。2025年全体・2026年8か月・9月15日間は長さが異なります。利益だけでなく、取引件数とコスト耐性を併記しました。', '',
        '## 追加期間の扱い', '',
        'モデルと設定のハッシュを保存してから、Dukascopyの2026年9月1日00:00UTC〜9月16日00:00UTC未満を取得。追加期間の結果を見てからモデル・閾値・通貨を変更していません。',
        '**ドル円の9月中旬は、以前のFinnhub仮想検証で市場の一部を確認済みです。研究全体として完全に未使用の最終テストとは呼べません。** 今回のモデル調整に使わなかった追加期間の確認です。15日間だけで将来利益は判断できません。', '',
        '## 学習・評価の分離', '',
        '2025年用は2021〜2023年で学習、2024年前半で確率校正、2024年後半を検証用に保存。2026年用は2022〜2024年で学習、2025年前半で校正、2025年後半を検証用に保存しました。翌年の価格は学習に混ぜていません。',
        'ただし、2025年・2026年1〜8月は前の実験でも見た期間で、今回の候補選びにも使用しています。探索的な過去比較です。検証用後半期間だけで選択した純粋な外部テスト成績と称していません。全モデル・全失敗条件を記録し、良い結果だけを抜き出した成果にはしていません。', '',
        '## コストと運転との差', '',
        '買いは次足ASK始値→保有終了足BID終値、売りは逆。観測スプレッド＋往復0.2pipの不利な約定ずれ＋往復0.005%手数料。厳しい条件はスプレッド2倍＋往復0.5pip＋同じ手数料です。',
        '手数料は[Dukascopy Japan掲載の片道最大25円/100万円](https://www.dukascopy.jp/)を参考にした固定条件。データ提供元と実際の取引口座のコストが同じとは限りません。',
        '注文可否に使うコスト推定は判断時点のスプレッドから計算し、将来の実スプレッドは使いません。損益採点では実際の出口BID/ASKを使用します。',
        '先の区間が欠けている判断は採点できないため除外しています。実運転では将来の切断は予知できず、通信障害・未決済建玉を含めた完全な運転シミュレーションではありません。決済時点の下落しか計算せず、保有中の含み損や円換算・実約定・証拠金を再現していません。', '',
        '## 現時点の判断', '',
        '利益が残る過去の組合せを見つけることと、今後も使えるモデルを確認することは別です。今回は少数取引の研究候補が残った段階です。稼働モデルへの置換、レバレッジの引上げ、実注文は行っていません。',
        '「多数の取引と安定したコスト後利益を両立する」という目標は未達。候補の設定を固定した後続データの蓄積が必要です。同じ期間を使ってプラスになるまで調整し続けた結果を、実力の証拠にはしません。', '',
        '## 検査・再現', '',
        'test_search.pyの3件で週末と平日欠損の区別、判断時点のコスト、非重複、他通貨特徴量の因果性を確認。verify_search.pyで96組の保存予測を再現し、288組の検証用・評価用取引集計を再計算しました。',
        'search.py → select_candidates.py → fresh_check.py → verify_search.py → report.py。protocol.jsonに当初条件、frozen_candidates.jsonに採用候補判定、watchlist_frozen.jsonに少数取引案の追加確認方針とモデルハッシュを保存しています。', '',
        '## 全72通りの評価結果', '',
        'baseは41特徴量、crossは他通貨を含む50特徴量。各年の通常コストと厳しいコストを並べています。', '',
        '| 通貨 | 分 | 特徴量 | 方式 | 2025件数 | 2025収益 | 厳しいコスト | 2026件数 | 2026収益 | 厳しいコスト |',
        '|---|---:|---|---|---:|---:|---:|---:|---:|---:|']
    for (pair,h,features,policy),g in test.groupby(['pair','horizon_minutes','features','policy']):
        a=g[g.year==2025].iloc[0];b=g[g.year==2026].iloc[0]
        lines.append(f'| {pair} | {h} | {features} | {POLICY[policy]} | {a.trades} | {a.return_pct:+.2f}% | {a.stress_return_pct:+.2f}% | {b.trades} | {b.return_pct:+.2f}% | {b.stress_return_pct:+.2f}% |')
    (ROOT/'REPORT_JA.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('REPORT COMPLETE',len(test),'historical evaluations;',len(fresh),'additional-period checks')


if __name__=='__main__':main()
