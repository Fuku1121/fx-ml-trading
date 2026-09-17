"""Aggregate all predefined runs, check accounting, and write a Japanese report."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
PAIRS=('USDJPY','EURUSD','GBPUSD','AUDUSD')


def portfolio(year,horizon,model):
    equity=[];stress_equity=[];trades=[];sessions=set();events=[]
    for pair in PAIRS:
        folder=ROOT/'runs'/f'{pair}_{year}_{horizon}m_{model}'
        t=pd.read_csv(folder/'trades.csv',parse_dates=['signal_time','entry','exit'])
        assert (t.net>=t.stress_net-1e-12).all()
        assert (t.entry.iloc[1:].to_numpy()>=t.exit.iloc[:-1].to_numpy()).all()
        metrics=json.loads((folder/'metrics.json').read_text())
        assert len(t)==metrics['trades']
        assert abs((np.prod(1+t.net)-1)*100-metrics['return_pct'])<1e-8
        sessions.update(pd.read_csv(folder/'market_sessions.csv').session.astype(str))
        curve=np.cumprod(1+t.net.to_numpy())
        exit_index=pd.DatetimeIndex(pd.to_datetime(t.exit,utc=True))
        equity.append(pd.Series(curve,index=exit_index,name=pair))
        stress_equity.append(pd.Series(np.cumprod(1+t.stress_net.to_numpy()),index=exit_index,name=pair))
        t['pair']=pair
        t['portfolio_cash_pnl']=.25*np.r_[1,curve[:-1]]*t.net if len(t) else []
        trades.append(t)
        for row in t.itertuples():
            events.extend([(row.entry,1),(row.exit,-1)])
    initial=pd.Timestamp(f'{year}-01-01',tz='UTC')
    def combine(series):
        frame=pd.concat(series,axis=1,sort=True).sort_index()
        frame.loc[initial]=1
        return frame.sort_index().ffill().fillna(1).mean(axis=1)
    curve=combine(equity);stress=combine(stress_equity)
    t=pd.concat(trades,ignore_index=True)
    assert abs(1+t.portfolio_cash_pnl.sum()-curve.iloc[-1])<1e-9
    maximum=active=0
    for _,delta in sorted(events,key=lambda e:(e[0],e[1])):
        active+=delta;maximum=max(maximum,active)
        assert 0<=active<=4
    daily=t.copy()
    if len(daily):
        daily['session']=(pd.to_datetime(daily.exit,utc=True).dt.tz_convert('America/New_York')+pd.Timedelta(hours=7)).dt.date.astype(str)
        daily=daily.groupby('session').portfolio_cash_pnl.sum().reindex(sorted(sessions),fill_value=0)
    else:daily=pd.Series(0.,index=sorted(sessions))
    # Moving 5-session block bootstrap for mean daily realized cash PnL.
    # Descriptive uncertainty only: does not correct for choosing across 32 runs.
    values=daily.to_numpy();rng=np.random.default_rng(42);means=[]
    for _ in range(2000):
        starts=rng.integers(0,max(1,len(values)-4),size=int(np.ceil(len(values)/5)))
        sample=np.concatenate([values[s:s+5] for s in starts])[:len(values)]
        means.append(sample.mean()*1e4)
    ci=np.quantile(means,[.025,.975])
    pd.DataFrame({'equity':curve,'stress_equity':stress.reindex(curve.index).ffill()}).to_csv(ROOT/f'portfolio_{year}_{horizon}m_{model}.csv')
    return dict(year=year,horizon_minutes=horizon,model=model,trades=len(t),market_days=len(sessions),
        trades_per_day=len(t)/len(sessions),return_pct=(curve.iloc[-1]-1)*100,
        stress_return_pct=(stress.iloc[-1]-1)*100,
        closed_drawdown_pct=(curve/curve.cummax()-1).min()*100,
        max_concurrent_positions=maximum,daily_pnl_bps_ci_low=ci[0],daily_pnl_bps_ci_high=ci[1])


def main():
    records=[json.loads(p.read_text()) for p in sorted((ROOT/'runs').glob('*/metrics.json'))]
    bands=[]
    for record in records:
        t=pd.read_csv(ROOT/'runs'/record['name']/'trades.csv')
        record['spread_only_return_pct']=float((np.prod(1+t.quoted_net)-1)*100)
        predictions=pd.read_csv(ROOT/'runs'/record['name']/'predictions.csv')
        confidence=np.maximum(predictions.p_up,1-predictions.p_up)
        correct=(predictions.p_up>=.5).astype(int)==predictions.target
        for lo,hi in ((.5,.55),(.55,.58),(.58,.6),(.6,.65),(.65,1.000001)):
            mask=(confidence>=lo)&(confidence<hi)
            bands.append({'name':record['name'],'confidence_low':lo,'confidence_high':min(hi,1),
                'count':int(mask.sum()),'mean_confidence':float(confidence[mask].mean()) if mask.any() else None,
                'direction_accuracy':float(correct[mask].mean()) if mask.any() else None})
    df=pd.DataFrame(records)
    assert len(df)==32 and df.name.is_unique
    df.to_csv(ROOT/'results.csv',index=False)
    pd.DataFrame(bands).to_csv(ROOT/'confidence_bands.csv',index=False)
    portfolios=pd.DataFrame([portfolio(y,h,m) for y in (2025,2026) for h in (30,60) for m in ('HGB','logistic')])
    portfolios.to_csv(ROOT/'portfolios.csv',index=False)
    price_returns=[]
    for pair in PAIRS:
        f=pd.concat([pd.read_csv(ROOT/'data'/f'{pair}_{year}_B.csv',index_col='timestamp',parse_dates=True) for year in (2025,2026)])
        f.index=pd.to_datetime(f.index,utc=True)
        consecutive=f.index.to_series().diff()==pd.Timedelta(minutes=15)
        price_returns.append(f.close.pct_change().where(consecutive).rename(pair))
    corr=pd.concat(price_returns,axis=1,sort=True).dropna().corr()
    corr.to_csv(ROOT/'price_return_correlations.csv')
    most_active=portfolios.loc[portfolios.trades_per_day.idxmax()]
    lines=['# 複数通貨ペアの機械学習検証', '', '2026年9月17日実施。実行中Notebook・モデル・API接続・実注文は変更していません。', '',
        '**今回の32条件では、追加採用できる通貨・モデルの組合せは見つかりませんでした。** 新規3通貨は2026年の全条件でコスト後マイナス。これは今回のモデル・期間・品質・コスト条件の結果で、他の方法でも自動売買が不可能という意味ではありません。',
        f'4通貨合計で最も回数が多い条件は{most_active.model}・{int(most_active.horizon_minutes)}分先、{int(most_active.year)}年の平均{most_active.trades_per_day:.2f}回/日でした。ただし、その期間収益は{most_active.return_pct:+.2f}%、厳しいコストでは{most_active.stress_return_pct:+.2f}%です。取引回数を増やすことと利益を残すことは両立していません。', '',
        '## 検証の範囲', '',
        'USD/JPY、EUR/USD、GBP/USD、AUD/USDの4通貨。30分・60分先、HGB・ロジスティック回帰、2025年・2026年の計32条件を固定して比較しました。',
        '各通貨で別々に学習。既存モデルの41特徴量と主要HGB設定を引き継ぎ、閾値58%を維持しました。HGBは決定木を組み合わせる方式、ロジスティック回帰は比較用のシンプルな方式です。ドル円の学習済み重みを流用した結果ではありません。',
        '2025年評価は2021〜2023年で学習し2024年で確率校正。2026年評価は2022〜2024年で学習し2025年で校正、評価は8月末まで。境界をまたぐ将来ラベルを除外しています。',
        'データはDukascopyの15分BID・ASK。年ごとに取得してハッシュを保存。USD/JPYの一部BIDは以前取得した同一配信元の年別ファイルを再利用しました。',
        '過去150本の連続足と将来4本の連続足を要求し、欠損を埋めていません。週末後も150本まで待つ厳格な比較であり、現在のgap-aware仮想運転と同一条件ではありません。回数の分母は待機日・注文0日も含む観測市場セッションです。',
        '将来区間が欠けた判断は採点対象から除外しています。運転時には将来の欠損を予知できないため、これはデータがそろった区間のモデル比較であり、通信障害時の建玉処理まで再現した完全な運転シミュレーションではありません。', '',
        '## 自動売買への接続可能性', '',
        'この4通貨には国内業者の取扱いと自動発注に対応するプラットフォームがあります。通貨として対象にできることと、本人の口座で直ちにAPIを使えることは別です。実口座の利用可否や注文接続は今回テストしていません。',
        '[OANDA自動売買/API](https://www.oanda.jp/platform/api)、[OANDA取扱通貨の掲載マニュアル](https://www.oanda.jp/pdf/fxTrade_Android_Manual.pdf)、[Dukascopy Japan JForex](https://www.dukascopy.jp/trading-platforms/jforex/platform/)。',
        'OANDAのREST APIにはGold・プロコース・残高25万円以上などの条件が記載されています。以前の資金10万円案で、そのAPIがすぐ使えるとは限りません。JForexの自動売買はJava実装で、Pythonモデルからの接続には別実装が必要です。', '',
        '## 損益計算', '',
        '方向の正解は次足始値から対象足終値までの中値変化。注文は買いならASK始値→BID終値、売りならBID始値→ASK終値。同一通貨内は同時保有せず、通貨単独の表は固定1倍相当です。',
        '観測スプレッドに往復0.2pipの不利な約定ずれと往復0.005%の手数料を加算。厳しい条件ではスプレッド2倍・往復0.5pip・同じ手数料です。手数料は[Dukascopy Japan掲載の片道最大25円/100万円](https://www.dukascopy.jp/)を参考にした固定仮定で、本人の契約条件ではありません。',
        '以下の収益は評価期間全体で、年率ではありません。実際の約定・スワップ・含み損中の最大下落・証拠金・円換算為替変動は再現していません。配信元BID/ASKの足始値・終値は同時刻の約定可能なティックとは限りません。', '',
        '## 通貨ごとの結果', '',
        '的中率は注文しない判断も含む方向予測の成績。勝率はコスト後プラスの取引割合で、別の指標です。', '',
        '| 通貨 | 年 | 予測 | 学習器 | 的中率 | 回/日 | 勝率 | 期間収益 | 厳しいコスト | 決済時の最大下落 |',
        '|---|---:|---:|---|---:|---:|---:|---:|---:|---:|']
    for r in df.sort_values(['pair','model','horizon_minutes','year']).itertuples():
        win='—' if pd.isna(r.win_rate) else f'{r.win_rate:.1%}'
        lines.append(f'| {r.pair} | {r.year} | {r.horizon_minutes}分 | {r.model} | {r.accuracy:.1%} | {r.trades_per_day:.2f} | {win} | {r.return_pct:+.2f}% | {r.stress_return_pct:+.2f}% | {r.closed_drawdown_pct:.2f}% |')
    lines += ['', '## 4通貨を合わせた結果', '',
        '初期資金を各通貨25%ずつの4口に分け、各口で独立して1倍運用。各通貨の損益率を単純合計した成績ではありません。途中の配分変更はしません。', '',
        '| 年 | 予測 | 学習器 | 合計回/日 | 期間収益 | 厳しいコスト | 決済時の最大下落 | 最大同時保有 |',
        '|---|---:|---|---:|---:|---:|---:|---:|']
    for r in portfolios.itertuples():
        lines.append(f'| {r.year} | {r.horizon_minutes}分 | {r.model} | {r.trades_per_day:.2f} | {r.return_pct:+.2f}% | {r.stress_return_pct:+.2f}% | {r.closed_drawdown_pct:.2f}% | {r.max_concurrent_positions} |')
    lines += ['', '## 通貨間の値動きの重なり', '',
        '2025年〜2026年8月の共通15分リターンの相関です。相関1は同方向、-1は逆方向に動く傾向を示します。売買方向によっては逆相関の通貨でも同時に損失が出るため、4通貨を独立した機会とは扱いません。', '',
        '| | USDJPY | EURUSD | GBPUSD | AUDUSD |', '|---|---:|---:|---:|---:|']
    for pair in PAIRS:lines.append('| '+pair+' | '+' | '.join(f'{corr.loc[pair,p]:.2f}' for p in PAIRS)+' |')
    stable=[]
    for key,g in df.groupby(['pair','horizon_minutes','model']):
        if len(g)==2 and (g.stress_return_pct>0).all():stable.append('/'.join(map(str,key)))
    lines += ['', '## 判断', '',
        f'両評価期間で厳しいコストでもプラスだった通貨・モデルの組合せ：{", ".join(stable) if stable else "なし"}。',
        f'4通貨合計の平均取引回数は最大{portfolios.trades_per_day.max():.2f}回/日でした。',
        '複数候補を調べた探索研究であり、良い結果を選ぶことによる過大評価があり得ます。2026年で選んだ案を2025年でも良かったとして、完全な未使用データで検証済みとは扱いません。',
        'portfolios.csvには5市場セッション単位のブロック再抽出による日次実現損益の95%範囲も保存しています。候補選択の補正や将来利益の保証ではありません。',
        '採用前には設定を固定し、今後の同じ価格ストリームで現行モデルと並べて観察する必要があります。今回のモデルファイルは研究用で、稼働モデルへの配備はしていません。', '',
        '## 再現と検査', '',
        'download.py → research.py → report.py。run_when_ready.pyは各通貨の取得完了後に学習します。test_research.pyの5件で売買価格・将来特徴量の不変性・閾値・非重複・最初の損失・取引0件を検査。各32条件の取引件数と収益、ストレスコスト、ポートフォリオ現金損益の一致も検査しました。',
        'verify.pyで48入力ファイルのハッシュ・行数と、保存した32モデルによる全予測の再現を確認済み。差は1e-12未満です。検証結果とライブラリのバージョンはverification.jsonに保存しました。',
        'data_manifest.json / reused_data.json：入力とハッシュ。protocol.json：事前固定条件。data_audit_*.json：品質除外数。results.csv：32条件とスプレッドだけを考慮した参考損益。confidence_bands.csv：確率帯別の実際の的中率（重複する予測区間を含む）。portfolios.csv：8通りの合算。runs/：モデル・予測・全取引。']
    (ROOT/'REPORT_JA.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(df[['pair','year','model','horizon_minutes','trades_per_day','return_pct','stress_return_pct']].to_string(index=False))
    print(portfolios.to_string(index=False))
    print('CHECKED AND REPORTED',len(df),len(portfolios),flush=True)


if __name__=='__main__':main()
