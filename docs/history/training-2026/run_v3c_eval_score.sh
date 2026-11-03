#!/bin/bash
# v3c pipeline: wait for ollama import -> eval 50 -> real reference_checks score
set -u
LL="C:/Users/Administrator/AppData/Roaming/haolo_desktop/thread-groups/default/outputs/llm-lab"
PY="C:/Users/Administrator/.workbuddy/binaries/python/envs/llm_lab/Scripts/python.exe"
export PY

echo "[$(date +%H:%M:%S)] waiting for copilot-3b-lora-v3c in ollama..."
for i in $(seq 1 40); do
  if ollama list 2>/dev/null | grep -qi "copilot-3b-lora-v3c"; then
    echo "[$(date +%H:%M:%S)] v3c imported OK"; break
  fi
  sleep 10
done

echo "[$(date +%H:%M:%S)] starting v3c eval (50 samples)..."
cd "$LL" || exit 1
unset ACC_PRODUCT_CONFIG_V3
"$PY" -m llm_lab run examples/copilot_eval_3b_lora_v3c.yaml 2>&1 | tail -15

# locate the newest v3c run dir
RUN=$(ls -dt "$LL/runs"/*copilot*3b_lora_v3c* 2>/dev/null | head -1)
echo "[$(date +%H:%M:%S)] run dir: $RUN"
if [ -z "$RUN" ]; then echo "NO RUN DIR FOUND"; exit 1; fi

echo "[$(date +%H:%M:%S)] scoring with reference_checks..."
"$PY" scripts/score_copilot_run.py "$RUN" --dataset examples/copilot_eval/few_shot_v3.2.jsonl 2>&1 | tail -20

echo "[$(date +%H:%M:%S)] === V3C FINAL SCORE ==="
"$PY" -c "
import json
d=json.load(open('$RUN/copilot_scores.json',encoding='utf-8'))['summary']
print('score=%.2f%%' % (d.get('score',0)*100))
print('passed_reference_checks=%s/%s' % (d.get('passed_reference_checks'), d.get('total_reference_checks')))
print('yaml_parse_valid=%s/%s' % (d.get('yaml_parse_valid_count'), d.get('outputs')))
print('unsupported_claims=%s' % d.get('unsupported_claims'))
" 2>&1 | tail -8
echo "[$(date +%H:%M:%S)] DONE"
