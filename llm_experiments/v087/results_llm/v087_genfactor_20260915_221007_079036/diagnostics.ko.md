# v087 바이트·실패 진단

같은 원문 입력과 반복 seed는 독립 문제 수를 늘리지 않는다. 오류코드는 한 graph에서 겹칠 수 있다. facts 요청이 같아도 모델 출력이 반드시 같다는 가정은 하지 않는다.

| 구분 | 호출 | seed 포함 고유 | seed 제외 고유 |
|---|---:|---:|---:|
| end_to_end/allocated_id/facts | 128 | 128 | 128 |
| end_to_end/allocated_id/final | 128 | 128 | 128 |
| end_to_end/allocated_id/rule | 560 | 560 | 560 |
| end_to_end/baseline/facts | 128 | 128 | 128 |
| end_to_end/baseline/final | 128 | 128 | 128 |
| end_to_end/baseline/rule | 560 | 560 | 560 |
| end_to_end/inventory_allocated/facts | 128 | 128 | 128 |
| end_to_end/inventory_allocated/final | 128 | 128 | 128 |
| end_to_end/inventory_allocated/rule | 560 | 560 | 560 |
| end_to_end/node_inventory/facts | 128 | 128 | 128 |
| end_to_end/node_inventory/final | 128 | 128 | 128 |
| end_to_end/node_inventory/rule | 560 | 560 | 560 |
| rule_probe/allocated_id/rule | 140 | 140 | 70 |
| rule_probe/baseline/rule | 140 | 140 | 70 |
| rule_probe/inventory_allocated/rule | 140 | 140 | 70 |
| rule_probe/node_inventory/rule | 140 | 140 | 70 |
| shared_compare | 128 | 40 | 20 |
| shared_select | 128 | 96 | 48 |

## 관측 실패
실패 행 수: 238. 규칙 진단과 전체 graph 실패는 분리한다.
- t003_node_inventory: premise_counter_mismatch
- t003_inventory_allocated: premise_counter_mismatch
- t004_baseline: duplicate_id,premise_counter_mismatch
- t006_node_inventory: premise_counter_mismatch
- t006_allocated_id: premise_counter_mismatch
- t009_baseline: premise_counter_mismatch
- t011_node_inventory: premise_counter_mismatch
- t012_node_inventory: premise_counter_mismatch
- t014_allocated_id: missing_parent
- t015_allocated_id: missing_parent
- t016_allocated_id: missing_parent
- t016_inventory_allocated: missing_parent
- t017_inventory_allocated: missing_parent
- t022_allocated_id: missing_parent
- t022_inventory_allocated: missing_parent
- t024_allocated_id: missing_parent
- t025_allocated_id: missing_parent
- t025_inventory_allocated: missing_parent
- t026_allocated_id: missing_parent
- t026_inventory_allocated: missing_parent
- t027_allocated_id: missing_parent
- t027_inventory_allocated: missing_parent
- t028_allocated_id: missing_parent
- t028_inventory_allocated: missing_parent
- t029_allocated_id: missing_parent
- t029_inventory_allocated: missing_parent
- t042_baseline: premise_counter_mismatch
- t042_node_inventory: duplicate_parent,premise_counter_mismatch
- t042_allocated_id: premise_counter_mismatch
- t042_inventory_allocated: premise_counter_mismatch
- t043_allocated_id: premise_counter_mismatch
- t044_allocated_id: premise_counter_mismatch
- t045_baseline: premise_counter_mismatch
- t045_node_inventory: duplicate_parent,premise_counter_mismatch
- t045_allocated_id: premise_counter_mismatch
- t045_inventory_allocated: premise_counter_mismatch
- t046_allocated_id: premise_counter_mismatch
- t047_allocated_id: missing_parent
- t047_inventory_allocated: missing_parent
- t048_baseline: premise_counter_mismatch
- t048_node_inventory: premise_counter_mismatch
- t048_allocated_id: premise_counter_mismatch
- t048_inventory_allocated: premise_counter_mismatch
- t049_allocated_id: premise_counter_mismatch
- t049_inventory_allocated: premise_counter_mismatch
- t050_allocated_id: missing_parent
- t050_inventory_allocated: missing_parent
- t051_allocated_id: missing_parent
- t051_inventory_allocated: missing_parent
- t052_allocated_id: missing_parent
- t052_inventory_allocated: missing_parent
- t053_baseline: premise_counter_mismatch
- t053_allocated_id: premise_counter_mismatch
- t053_inventory_allocated: premise_counter_mismatch
- t054_baseline: premise_counter_mismatch
- t054_allocated_id: premise_counter_mismatch
- t055_allocated_id: missing_parent
- t055_inventory_allocated: missing_parent
- t056_allocated_id: missing_parent
- t056_inventory_allocated: premise_counter_mismatch
- t057_allocated_id: missing_parent
- t057_inventory_allocated: missing_parent
- t062_allocated_id: missing_parent
- t062_inventory_allocated: missing_parent
- t063_allocated_id: missing_parent
- t063_inventory_allocated: missing_parent
- t064_allocated_id: missing_parent
- t064_inventory_allocated: missing_parent
- t065_allocated_id: missing_parent
- t065_inventory_allocated: missing_parent
- t066_allocated_id: missing_parent
- t066_inventory_allocated: missing_parent
- t067_allocated_id: missing_parent
- t067_inventory_allocated: missing_parent
- t068_allocated_id: missing_parent
- t068_inventory_allocated: missing_parent
- t069_allocated_id: premise_counter_mismatch
- t069_inventory_allocated: missing_parent
- t070_allocated_id: missing_parent
- t070_inventory_allocated: missing_parent
- t071_allocated_id: missing_parent
- t071_inventory_allocated: missing_parent
- t072_allocated_id: missing_parent
- t072_inventory_allocated: missing_parent
- t073_allocated_id: missing_parent
- t073_inventory_allocated: missing_parent
- t074_allocated_id: missing_parent
- t074_inventory_allocated: missing_parent
- t075_allocated_id: missing_parent
- t075_inventory_allocated: missing_parent
- t076_allocated_id: missing_parent
- t076_inventory_allocated: missing_parent
- t077_allocated_id: missing_parent
- t083_allocated_id: missing_parent
- t083_inventory_allocated: missing_parent
- t088_allocated_id: missing_parent
- t088_inventory_allocated: missing_parent
- t095_allocated_id: missing_parent
- t095_inventory_allocated: missing_parent
- t105_allocated_id: missing_parent
- t108_allocated_id: premise_counter_mismatch
- t109_inventory_allocated: missing_parent
- t110_allocated_id: missing_parent
- t110_inventory_allocated: missing_parent
- t111_allocated_id: missing_parent
- t111_inventory_allocated: missing_parent
- t120_allocated_id: missing_parent
- t120_inventory_allocated: missing_parent
- t121_baseline: premise_counter_mismatch
- t121_allocated_id: premise_counter_mismatch
- t121_inventory_allocated: premise_counter_mismatch
- t122_baseline: premise_counter_mismatch
- t122_node_inventory: premise_counter_mismatch
- t122_allocated_id: missing_parent,premise_counter_mismatch
- t122_inventory_allocated: premise_counter_mismatch
- t123_allocated_id: premise_counter_mismatch
- t123_inventory_allocated: premise_counter_mismatch
- t126_baseline: premise_counter_mismatch
- t126_node_inventory: premise_counter_mismatch
- t126_allocated_id: premise_counter_mismatch
- t126_inventory_allocated: missing_parent
- t127_allocated_id: premise_counter_mismatch
- t127_inventory_allocated: premise_counter_mismatch
- t132_allocated_id: missing_parent,premise_counter_mismatch
- t132_inventory_allocated: premise_counter_mismatch
- t133_baseline: premise_counter_mismatch
- t133_node_inventory: premise_counter_mismatch
- t133_allocated_id: premise_counter_mismatch
- t133_inventory_allocated: premise_counter_mismatch
- t136_allocated_id: missing_parent
- t136_inventory_allocated: premise_counter_mismatch
- t137_node_inventory: premise_counter_mismatch
- t137_allocated_id: premise_counter_mismatch
- t137_inventory_allocated: premise_counter_mismatch
- t138_baseline: premise_counter_mismatch
- t138_allocated_id: missing_parent
- t138_inventory_allocated: missing_parent
- t139_allocated_id: premise_counter_mismatch
- t139_inventory_allocated: premise_counter_mismatch
- t142_baseline: premise_counter_mismatch
- t142_node_inventory: premise_counter_mismatch
- t142_inventory_allocated: premise_counter_mismatch
- t143_allocated_id: premise_counter_mismatch
- t143_inventory_allocated: premise_counter_mismatch
- t148_allocated_id: missing_parent
- t148_inventory_allocated: missing_parent
- t149_baseline: premise_counter_mismatch
- t149_node_inventory: premise_counter_mismatch
- t149_allocated_id: premise_counter_mismatch
- t149_inventory_allocated: premise_counter_mismatch
- t154_allocated_id: missing_parent
- t154_inventory_allocated: missing_parent
- t155_allocated_id: missing_parent
- t155_inventory_allocated: missing_parent
- t160_allocated_id: missing_parent
- t160_inventory_allocated: missing_parent
- t161_allocated_id: missing_parent
- t161_inventory_allocated: missing_parent
- t164_allocated_id: missing_parent
- t164_inventory_allocated: missing_parent
- t165_allocated_id: missing_parent
- t165_inventory_allocated: missing_parent
- t166_allocated_id: missing_parent
- t166_inventory_allocated: missing_parent
- t167_allocated_id: missing_parent
- t167_inventory_allocated: missing_parent
- t170_allocated_id: premise_counter_mismatch
- t170_inventory_allocated: premise_counter_mismatch
- t171_allocated_id: missing_parent
- t171_inventory_allocated: missing_parent
- t176_allocated_id: missing_parent
- t177_allocated_id: missing_parent
- t177_inventory_allocated: missing_parent
- t180_allocated_id: missing_parent
- t181_allocated_id: missing_parent
- t181_inventory_allocated: missing_parent
- t182_allocated_id: premise_counter_mismatch
- t183_allocated_id: missing_parent
- t183_inventory_allocated: missing_parent
- t192_inventory_allocated: missing_parent
- t193_allocated_id: missing_parent
- t193_inventory_allocated: missing_parent
- t194_allocated_id: missing_parent
- t194_inventory_allocated: missing_parent
- t195_allocated_id: premise_counter_mismatch
- t195_inventory_allocated: missing_parent
- t198_allocated_id: missing_parent
- t198_inventory_allocated: missing_parent
- t199_allocated_id: premise_counter_mismatch
- t199_inventory_allocated: missing_parent
- t204_allocated_id: premise_counter_mismatch
- t204_inventory_allocated: missing_parent
- t205_allocated_id: missing_parent
- t205_inventory_allocated: missing_parent
- t208_allocated_id: premise_counter_mismatch
- t209_allocated_id: missing_parent
- t209_inventory_allocated: premise_counter_mismatch
- t210_allocated_id: premise_counter_mismatch
- t210_inventory_allocated: premise_counter_mismatch
- t211_allocated_id: missing_parent,premise_counter_mismatch
- t211_inventory_allocated: missing_parent
- t214_allocated_id: missing_parent
- t214_inventory_allocated: missing_parent
- t215_allocated_id: premise_counter_mismatch
- t215_inventory_allocated: missing_parent
- t220_allocated_id: premise_counter_mismatch
- t221_baseline: premise_counter_mismatch
- t221_allocated_id: missing_parent,premise_counter_mismatch
- t221_inventory_allocated: premise_counter_mismatch
- d00s0_deep_r03_inventory_allocated: premise_counter_mismatch
- d00s0_deep_r03_baseline: premise_counter_mismatch
- d00s0_deep_r03_node_inventory: premise_counter_mismatch
- d00s0_deep_r03_allocated_id: premise_counter_mismatch
- d00s1_deep_r03_node_inventory: premise_counter_mismatch
- d00s1_deep_r03_allocated_id: premise_counter_mismatch
- d00s1_deep_r03_inventory_allocated: premise_counter_mismatch
- d00s1_deep_r03_baseline: premise_counter_mismatch
- d02s0_shallow_r02_node_inventory: premise_counter_mismatch
- d02s0_shallow_r02_allocated_id: premise_counter_mismatch
- d02s0_shallow_r02_inventory_allocated: premise_counter_mismatch
- d02s0_shallow_r03_node_inventory: premise_counter_mismatch
- d02s0_shallow_r03_allocated_id: premise_counter_mismatch
- d02s0_shallow_r03_inventory_allocated: premise_counter_mismatch
- d02s0_shallow_r03_baseline: premise_counter_mismatch
- d02s0_shallow_r04_allocated_id: premise_counter_mismatch
- d02s0_deep_r04_inventory_allocated: premise_counter_mismatch
- d02s1_shallow_r04_allocated_id: premise_counter_mismatch
- d02s1_shallow_r03_node_inventory: premise_counter_mismatch
- d02s1_shallow_r03_allocated_id: premise_counter_mismatch
- d02s1_shallow_r03_inventory_allocated: premise_counter_mismatch
- d02s1_shallow_r03_baseline: premise_counter_mismatch
- d02s1_shallow_r02_allocated_id: premise_counter_mismatch
- d02s1_shallow_r02_inventory_allocated: premise_counter_mismatch
- d02s1_shallow_r02_node_inventory: premise_counter_mismatch
- d05s0_shallow_r04_allocated_id: premise_counter_mismatch
- d05s0_shallow_r04_baseline: premise_counter_mismatch
- d05s1_shallow_r04_allocated_id: premise_counter_mismatch
- d05s1_shallow_r04_baseline: premise_counter_mismatch
