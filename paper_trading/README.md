# 仮想売買の参照コード

Finnhubの観測価格を保存し、2モデル・3仮想口座を同じ期間で評価するPythonコードです。実注文APIはありません。[運転状況と評価条件](../docs/CLOUD_PAPER_20260917.md) を先に読むと全体像を追えます。

## コードを読む順番

| ファイル | 役割 |
|---|---|
| protocol.json | 期間、足の品質、費用、売買判断の固定条件 |
| collector.py / quality.py | 価格観測を保存し、完全な足と観測抜けを区別 |
| history.py | 4通貨の時刻をそろえ、予測に渡せる履歴か確認 |
| frozen_inference.py / predictors.py | 特徴量の計算と保存済みモデルの推論 |
| engine.py | 注文待ち、仮想約定、決済、停止、口座状態の保存 |
| runner.py | 単一接続で収集・判断・保存を進める制御 |
| report.py / healthcheck.py | 成績と稼働状態を読み取る |
| backup.py | SQLiteの整合した複製を作る |
| capital_plan.py | 同じ取引に別の資金・積立条件を当てはめる |
| test_*.py | 状態遷移、再起動、欠損、費用、資金計画の検査 |
| deploy/ | systemd設定例。バックアップの設定例は未有効化 |

実行ロジックは稼働パッケージの写しです。GitHub用にモデル不在時のテストを明示的にskipする処理だけ追加しました。稼働中のモデル、コード、条件、状態は変更していません。

## APIキーなしでテストする

Python 3.13の独立した仮想環境を使います。以下はリポジトリのルートから実行します。

```bash
python -m venv .venv-paper
# Linux/macOS: source .venv-paper/bin/activate
# Windows PowerShell: .venv-paper/Scripts/Activate.ps1
python -m pip install -r paper_trading/requirements.txt
python -m unittest discover -s paper_trading -p 'test_*.py' -v
```

30件のうち、配布していない学習済みモデルを使う1件はskipになります。残る29件は一時ディレクトリと合成価格を用い、API接続や実注文はしません。モデル付きの元環境では30件すべてを検査済みです。

## 配布物の範囲

このフォルダはコードレビューとオフライン検査用で、単独で常時運転を始める完成パッケージではありません。`model/` 内の学習済みモデル・manifest・特徴量一覧、稼働状態、認証情報は同梱しません。`bundle_hashes.json` は配備済みパッケージの元の照合記録であり、この閲覧用コピー全体のハッシュではありません。元の文書やモデルがないため、`runner.py` の完全なパッケージ検査はこのコピーだけでは通りません。検査を無効にして運転しないでください。

`probe.py` は手動の実接続検査、`runner.py` は継続収集です。テスト用コマンドと区別してください。`deploy/` は元パッケージを所定の場所に配置済みであることを前提とする設定例です。

資金シナリオの前提は [CAPITAL_PLAN_JA.md](CAPITAL_PLAN_JA.md) に記載しています。勝率、入金、含み損、コストの扱いを読み分けて評価します。
