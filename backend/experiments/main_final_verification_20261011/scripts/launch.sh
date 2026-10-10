#!/bin/bash
# usage: launch.sh <split development|evaluation> <shards>
# Bundles main ad9597f backend/app + predictor files (no truth, no scorer), uploads once,
# runs an offline preflight per shard, then starts one container per shard.
set -euo pipefail
SPLIT=$1; SHARDS=$2
X="$(cd "$(dirname "$0")/.." && pwd)"
KEY=${GPU_SSH_KEY:?set}; HOST=${GPU_SSH_TARGET:?set user@host}
R=/data/work/efficiency-main-final-20261011
IMG=cbh-cloud-worker:20261010-42e9f31
SSH="ssh -i $KEY -p ${GPU_SSH_PORT:?set} -o BatchMode=yes $HOST"
# Each split gets its own frozen code directory (development ran the first bundle in $R/code).
CODE=$R/code_$SPLIT
BUNDLE="$X/scripts/bundle_$SPLIT.tar"
if ! $SSH "test -d $CODE"; then
  rm -rf "$X/scripts/stage"; mkdir -p "$X/scripts/stage/experiment"
  cp -R "$X/source_ad9597f/backend" "$X/scripts/stage/backend"
  cp "$X/scope.json" "$X/inputs.json" "$X/run_main.py" "$X/scripts/stage/experiment/"
  find "$X/scripts/stage" -name "__pycache__" -prune -exec rm -rf {} +
  COPYFILE_DISABLE=1 tar --no-xattrs -C "$X/scripts/stage" -cf "$BUNDLE" backend experiment
  SHA=$(shasum -a 256 "$BUNDLE" | cut -d' ' -f1); echo "$SHA" > "$X/scripts/bundle_$SPLIT.sha256"
  $SSH "mkdir -p $CODE $R/output $R/usage && chmod 700 $R"
  scp -q -i $KEY -P ${GPU_SSH_PORT} -o BatchMode=yes "$BUNDLE" "$HOST:$R/bundle_$SPLIT.tar"
  $SSH "cd $R && echo '$SHA  bundle_$SPLIT.tar' | sha256sum -c - && tar -xf bundle_$SPLIT.tar -C $CODE 2>/dev/null; test ! -e $CODE/experiment/truth_private.json && test ! -e $CODE/experiment/evaluate_main.py"
fi
COMMON="sudo -n docker run --read-only --user 7778:7778 --cpus 1.5 --memory 6g --tmpfs /tmp:rw,size=512m,mode=1777 \
 --add-host host.docker.internal:host-gateway -e PYTHONPATH=/experiment/backend -e OMP_NUM_THREADS=1 -e PYTHONDONTWRITEBYTECODE=1 \
 -v $CODE:/experiment:ro -v $R/output:/evidence:rw -v $R/usage:/usage:rw -v /data/work/cbh-gpu-staging/assets:/assets:ro \
 -v /data/work/cbh-app-flow-20261010/worker.env:/run/ai.env:ro -w /experiment/backend --entrypoint python"
for k in $(seq 0 $((SHARDS-1))); do
  NAME=eff-main-${SPLIT:0:3}-s$k
  $SSH "$COMMON --rm --network none --name $NAME-pre $IMG /experiment/experiment/run_main.py --split $SPLIT --shard $k --shards $SHARDS > $R/preflight_$NAME.log 2>&1 || { tail -20 $R/preflight_$NAME.log; exit 1; }"
  $SSH "$COMMON -d --network cbh-cloud-worker_default --name $NAME $IMG /experiment/experiment/run_main.py --execute --split $SPLIT --shard $k --shards $SHARDS"
done
$SSH "sudo -n docker ps --filter name=eff-main --format '{{.Names}} {{.Status}}'; date -Is"
