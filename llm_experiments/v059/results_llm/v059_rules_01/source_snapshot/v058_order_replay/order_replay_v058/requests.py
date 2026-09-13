"""No prompt transformation and no scoring imports."""
from .contracts import strict_json, unb64, require
from selection_probe_v057.requests import schema_for

def request_bytes(plan, slot):
    require(slot['mode'] in ('graph', 'choice'), 'Unknown mode')
    raw = unb64(plan['reference']['request_bank'][slot['reference_slot_id']])
    q = strict_json(raw)
    require(q['model'] == plan['identities'][slot['model_key']]['model'], 'Model mismatch')
    require(q['options']['seed'] == slot['seed'], 'Seed mismatch')
    return raw
