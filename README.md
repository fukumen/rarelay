# rarelay

`rarelay` は、特定のインターフェースから受信した IPv6 Router Advertisement (RA) パケットを解析し、RDNSS (Recursive DNS Server) や DNSSL (DNS Search List) を注入して別のインターフェースへ再送するためのツールです。

## 作成の目的
HGW（ホームゲートウェイ）などのルーターにおいて、RDNSS や DNSSL をユーザー側で自由に変更できないという制限を回避するために作成されました。本来のルーターが送信するプレフィックス情報はそのままに、任意の DNS 情報をクライアントに配布することを目的としています。

## 主な機能
- `ethsrc` で受信した RA パケットを解析し、`ethdst` へ再送します。
- RA パケットに含まれる Prefix Info オプションに基づき、指定した RDNSS や DNSSL を注入します。
- Router Solicitation (RS) パケットに応答し、最新の RA を送信します。
- RA の有効期限に基づいた定期的な RA の再送を行います。

## 動作の仕組み
`rarelay` は、以下の 2 つのタイミングで RA パケットを送信します。

1. **中継と定期的な再送**:
   * `ethsrc` で受信したルーターからの RA を解析し、`ethdst` へ中継送信します。
   * その後、受信したプレフィックスの有効期限（Valid Lifetime）が切れる **30秒前** に、ルーターからの定期送信がなくても `rarelay` が自律的に RA を再送信します。
   * それ以降は、最新の設定を維持するために定期的に RA の送信を継続します。
2. **RS (Router Solicitation) への即時応答**:
   * クライアントが送信する RS パケットを `rssrc` で検知すると、ルーターに代わって最新の RA を即座に返信します。これにより、クライアントはルーターからの次の定期送信を待たずに設定を完了できます。

## 想定されるネットワーク構成
このツールは、スイッチによるパケット制御と組み合わせて、本来のルーターからの RA が直接クライアントに届かないように隔離して運用することを想定しています。

具体的な事例として、Mikrotik スイッチを使用してパケットの流れを制御し、`rarelay` を介入させる構成例を以下に記載しています。

- [Mikrotik を使用したネットワーク構成例](NETWORK_EXAMPLE.md)

## 必要条件
- Python 3.x
- [Scapy](https://scapy.net/) (`pip install scapy`)

## セットアップ
1. `rarelay.py` を任意の場所に配置します。
2. `samples/config.py` を `rarelay.py` と同じディレクトリにコピーし、環境に合わせて設定を編集します。

### 設定 (`config.py`)
- `ethsrc`: RA を受信するソースインターフェース。
- `ethdst`: RA を送信するターゲットインターフェース。
- `rssrc`: RS を監視するインターフェース (`ethsrc` または `ethdst`)。
- `dns`: 注入する DNS サーバーのアドレス（Prefix は RA から自動補完）。
- `searchlist`: 注入する DNS 検索ドメインリスト。

## システムサービスへの登録 (`samples/rarelay.service`)
`systemd` 経由でバックグラウンド実行が可能です。
1. `/etc/systemd/system/rarelay.service` にファイルを配置します。
   * **注意**: `ExecStart` のパス（`/path/to/rarelay.py`）を、実際にファイルを置いたフルパスに書き換えてください。
2. `systemctl daemon-reload`
3. `systemctl enable --now rarelay.service`

## デバッグとモニタリング (`samples/ratshark.service`)
`tshark` を使用してルーターから届く RA パケットをキャプチャするためのサービスです。利用には `tshark` がインストールされている必要があります。
1. `/etc/systemd/system/ratshark.service` にファイルを配置します。
   * **注意**: `ExecStartPre` および `ExecStart` 内のパス（`/path/to/`）を、実際の保存先に合わせて書き換えてください。
2. ルーター側のインターフェース (**`ethsrc`**) の RA パケットのみをフィルタリングして保存します。

## 仮想環境での利用
Linux ブリッジを経由する環境（Proxmox や LXD など）では、マルチキャストスヌーピングにより RS パケットを受信できないことがあります。その場合は `smcroute` を使用して回避可能です。

### 回避手順
1. `smcroute` をインストールします。
2. `rssrc` のインターフェースで `ff02::2` (All-Routers) グループに参加するように設定を永続化します。
   `/etc/smcroute.conf` に以下を追加します（例: `eth0` の場合）。
   ```conf
   mgroup from eth0 group ff02::2
   ```
3. `smcroute` サービスを有効化・再起動します。

### Proxmox LXCでの物理NICパススルー設定
VMではWeb GUIからパススルー設定が可能ですが、LXCコンテナでUSBイーサネットアダプタなどの物理NICを `ethsrc` として使用する場合は、構成ファイル（`/etc/pve/lxc/ID.conf`）を直接編集してパススルー設定を行う必要があります。

**LXC構成ファイルの設定例:**
```text
lxc.net.1.type: phys       # 必ず最初に記述
lxc.net.1.link: enp0s20u2  # ホスト側のUSB NIC名
lxc.net.1.name: eth1       # コンテナ内でのデバイス名(ethsrc)
```

**重要な注意点:**
- **Proxmoxの特例**: 通常、非特権コンテナ（Unprivileged container）での物理NICパススルーは制限されますが、Proxmoxではホスト側が処理を代行するため、非特権コンテナでも利用可能です。

## 注意事項
- **実行権限**: Raw Socket を使用するため、実行には root 権限が必要です。
- **プレフィックス長の制限**: 現在、IPv6 プレフィックス長が **64ビット** であることを前提としています。
