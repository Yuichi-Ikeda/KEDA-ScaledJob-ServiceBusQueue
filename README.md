# KEDA による AKS スケールアウト検証

Azure Service Bus Queue をトリガーとした KEDA による AKS スケールアウト検証として、プール辺り最大の 1,000 ノードまでのスケールアウトを実施検証する。
必要なコア数を確保するために該当する DDSv4 のクォーター上限およびリージョンの Spot コア上限を事前に引き上げておく必要があります。

## 考慮事項

- [Azure Container Registry サービス階層](https://learn.microsoft.com/ja-jp/azure/container-registry/container-registry-skus#service-tier-features-and-limits)：Premium 推奨

- [専用のシステムノード プール](https://learn.microsoft.com/ja-jp/azure/aks/use-system-pools?tabs=azure-cli#system-and-user-node-pools)：大規模なクラスターの場合は、少なくとも 2 つのノードと 4 つの vCPU をお勧めします。

- [エフェメラル OS ディスク構成](https://learn.microsoft.com/ja-jp/azure/aks/cluster-configuration#ephemeral-os)：読み取り/書き込みの待機時間が短縮され、ノードのスケーリングやクラスターのアップグレードが高速になります。

- [AKS で Azure CNI オーバーレイ ネットワークを構成する](https://learn.microsoft.com/ja-jp/azure/aks/azure-cni-overlay#choosing-a-network-model-to-use)

- [AKS クラスターに Azure スポット ノード プールを追加する](https://learn.microsoft.com/ja-jp/azure/aks/spot-node-pool)

- [Premium ブロック BLOB ストレージ アカウント](https://learn.microsoft.com/ja-jp/azure/storage/blobs/storage-blob-block-blob-premium)

## クラスタ環境のデプロイ

Azure ポータルの [Cloud Shell](https://learn.microsoft.com/ja-jp/azure/cloud-shell/quickstart?tabs=azurecli) にて実行します。

```bash
# 環境変数の定義
export RESOURCE_GROUP=AKS-AutoScale-Cluster-group
export LOCATION=japaneast
export CLUSTER_NAME=AutoScale-Cluster
export ACR_NAME=<Unique ACR Name>
export STORAGE_ACCOUNT=<Unique Storage Account>
export SB=sb-keda-space
export SBQ=sbq-keda-queue
export SBQ_AUTH_MGMT=sbq-keda-queue-auth-mgmt

# リソースグループの作成
az group create -n $RESOURCE_GROUP -l $LOCATION

# コンテナレジストリの作成
az acr create -n $ACR_NAME -g $RESOURCE_GROUP --sku premium

# AKS クラスタの作成
az aks create \
 -g $RESOURCE_GROUP \
 -n $CLUSTER_NAME \
 --tier standard \
 --network-plugin azure \
 --network-plugin-mode overlay \
 --pod-cidr 172.16.0.0/12 \
 --nodepool-name system \
 --node-count 2 \
 --node-vm-size Standard_D4ds_v5 \
 --node-osdisk-type Ephemeral\
 --generate-ssh-keys \
 --attach-acr $ACR_NAME

# スケール対象のノードプール追加
az aks nodepool add \
 --resource-group $RESOURCE_GROUP \
 --cluster-name $CLUSTER_NAME \
 --priority Spot \
 --eviction-policy Delete \
 --enable-cluster-autoscaler \
 --min-count 0 \
 --max-count 998 \
 --nodepool-name worker \
 --node-count 0 \
 --node-vm-size Standard_D4ds_v4 \
 --node-osdisk-size 75 \
 --node-osdisk-type Ephemeral

# ストレージの作成（タスク結果の出力先）
az storage account create \
 -g $RESOURCE_GROUP \
 -n $STORAGE_ACCOUNT \
 -l $LOCATION \
 --sku Premium_LRS \
 --kind BlockBlobStorage \
 --min-tls-version TLS1_2 \
 --allow-blob-public-access false

# Service Bus の Namespace 作成
az servicebus namespace create \
 --resource-group $RESOURCE_GROUP \
 --name $SB \
 --sku basic

# Service Bus の Queue 作成
az servicebus queue create \
 --resource-group $RESOURCE_GROUP \
 --namespace-name $SB \
 --name $SBQ

# Service Bus Queue のアクセスポリシー作成
az servicebus queue authorization-rule create \
 --resource-group $RESOURCE_GROUP  \
 --namespace-name  $SB \
 --queue-name $SBQ \
 --name $SBQ_AUTH_MGMT \
 --rights Manage Send Listen
```
## KEDA のインストール

クラスターがデプロイ完了したら、KEDA のインストールをします。

```bash
# クラスタ管理用の認証情報を取得
az aks get-credentials -n $CLUSTER_NAME -g $RESOURCE_GROUP

# KEDA のインストール
kubectl apply -f https://github.com/kedacore/keda/releases/download/v2.10.1/keda-2.10.1.yaml
```

## コンテナイメージの Build と Azure Container Registry への Push

ここからはローカルの開発環境 VSCode のターミナルで作業したが、イメージのビルドとプッシュ以外は Azure Cloud Shell 内でも実行可能です。

```bash
# Azure 及び ACR へログイン
az login
az acr login -n <Unique ACR Name>

# コンテナイメージの Build
docker build . -t <Unique ACR Name>.azurecr.io/receive:0005

# ビルドしたイメージを ACR へ Push
docker push <Unique ACR Name>.azurecr.io/receive:0005
```

## アプリケーションを AKS へ展開

```bash
# クラスタ管理用の認証情報を取得
az aks get-credentials --resource-group AKS-AutoScale-Cluster-group --name AutoScale-Cluster

# ScaledJob の設定 ※※※ YAML 内に SERVICE_BUS_CONNECTION の設定が必要 ※※※
kubectl apply -f scaled-job.yaml
```

## クライアント側

VSCode のターミナルを開いてポートフォワーディングの設定を実施

```bash
# send.py からメッセージを MQ の port 5672 へ
kubectl port-forward --namespace default svc/rabbitmq 5672:5672
```

更に別ターミナルを開いてポートフォワーディングの設定を追加実施

```bash
# MQ 監視サイト用の設定 http://127.0.0.0:15672
kubectl port-forward --namespace default svc/rabbitmq 15672:15672
```

更に別ターミナルを開いてクライアント send.py によりメッセージを投入します。

```bash
# send.py 実行に必要な環境変数の設定
export STORAGE_CONNECTION=<Azure Storage Connection String>
export SERVICE_BUS_CONNECTION=<Azure Service Bus Connection String>
export SERVICE_BUS_QUEUE_NAME=<Azure Service Bus Queue Name>

python send.py
```