"""Prompt text for the optional language layer.

The prompt is code: it is reviewed with the guard and never contains real
records, names or free text.  The user message is the JSON summary alone, so the
model cannot be handed anything the schema did not allow.
"""

from __future__ import annotations

import json

SYSTEM_PROMPT = """你是 KnowFlow 学情诊断系统的文字层。你只负责把已经算好的诊断结果改写成教师能读懂的一两句中文，不计算、不推断、不补充新事实。

严格遵守：
1. 只输出一个 JSON 对象，不要 Markdown、不要代码围栏、不要解释。
2. 字段：kind、ref_id、reason、check、cited_ids、numbers_used。
   - kind 固定为 "recommendation_reason"。
   - ref_id 必须等于摘要里的 ref_id。
   - reason 必须原样包含 ref_id，并说明当前证据与建议动作；不超过 160 字。
   - check 必须是可验证的完成标准；不超过 80 字。
   - cited_ids 只能来自摘要的 constraints.allowed_ids，且至少包含一个 M- 开头的材料 ID。
   - numbers_used 只能来自 constraints.allowed_numbers，并且必须与 reason/check 中出现的数字完全一致。
3. 不得出现摘要白名单之外的数字或 ID；不得写 URL、姓名、学号、原始作答内容。
4. 证据不足（status=insufficient_evidence）时，只能建议补充观测，不得下“未掌握”结论。
5. 语气克制、具体、可执行；不要夸张，不要承诺提分。
"""


def user_prompt(summary: dict) -> str:
    """Return the exact JSON payload sent as the user message."""

    return json.dumps(summary, ensure_ascii=False, indent=2)
