"""校验官（B4）：结构 / 枚举 / ID / 数值 / 引用 / 规则 / 内容 / 安全 分层校验与修复兜底。"""

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import rules

DISALLOWED_PATTERNS = [
    r"忽略(以上|之前|所有)(指令|规则)",
    r"system\s*prompt",
    r"泄露(密钥|密码|token)",
    r"绕过(校验|审核|限制)",
]
INJECTION_PATTERNS = [
    r"<\|.*?\|>",
    r"忽略.*?指令",
    r"你现在是.*?管理员",
]
VERSION = "validator-v2"


def _issue(layer: str, message: str) -> Dict:
    return {"layer": layer, "message": message}


def validate_json_shape(data: Any, required: Iterable[str]) -> List[Dict]:
    issues = []
    if not isinstance(data, (dict, list)):
        return [_issue("structure", "输出不是合法 JSON 对象/数组")]
    if isinstance(data, dict):
        for key in required:
            if key not in data:
                issues.append(_issue("structure", f"缺少字段 {key}"))
    return issues


def validate_enum(value: Any, allowed: Iterable[str], name: str) -> List[Dict]:
    if value is None:
        return []
    allowed = list(allowed)
    if value not in allowed:
        return [_issue("enum", f"{name} 取值 {value} 不在允许集合")]
    return []


def validate_ids(ids: Iterable[Any], allowed_ids: Iterable[Any], name: str) -> List[Dict]:
    allowed = set(allowed_ids)
    return [
        _issue("id", f"{name} 引用了不存在或未授权的 ID {item}")
        for item in ids
        if item not in allowed
    ]


def validate_number(value: Any, low: float, high: float, name: str) -> List[Dict]:
    if value is None:
        return []
    if not isinstance(value, (int, float)):
        return [_issue("numeric", f"{name} 不是数值")]
    if value < low or value > high:
        return [_issue("numeric", f"{name} 超出范围 [{low}, {high}]")]
    return []


def scan_text(text: Optional[str]) -> List[Dict]:
    if not text:
        return []
    issues = []
    for pattern in DISALLOWED_PATTERNS:
        if re.search(pattern, text, re.I):
            issues.append(_issue("content", f"命中禁用表达：{pattern}"))
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.I):
            issues.append(_issue("security", f"疑似提示词注入：{pattern}"))
    return issues


def _as_date(value: Any) -> Optional[date]:
    """把 AI 输出里的日期字段归一化为 date，无法识别时返回 None。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _collect_ids(value: Any, key: str) -> List[Any]:
    """从 items 列表里按字段名收集出现顺序稳定的 ID 集合。"""
    collected: List[Any] = []
    if not isinstance(value, list):
        return collected
    for item in value:
        if isinstance(item, dict) and item.get(key) is not None:
            collected.append(item[key])
    return collected


def validate_reference(
    payload: Dict,
    kp_field: str = "kp_ids",
    task_field: str = "task_ids",
    items_field: str = "items",
    allowed_kp_ids: Optional[Iterable[Any]] = None,
    allowed_task_ids: Optional[Iterable[Any]] = None,
) -> List[Dict]:
    """引用一致性：跨字段闭环校验（与只查单点白名单的 validate_ids 不同）。

    三条规则：
    1. payload 顶层声明的 kp_ids / task_ids 不得重复引用；
    2. items[].kp_id 必须被顶层 kp_ids 覆盖（声称"已包含"就要真的在里面）；
    3. 顶层 task_ids 必须与 items[].task_id 实际出现的全集完全一致。
    传入 allowed_* 白名单时，额外要求引用落在白名单内。
    """
    issues: List[Dict] = []
    items = payload.get(items_field)

    declared_kp = payload.get(kp_field)
    if isinstance(declared_kp, list):
        seen: set = set()
        dup = [x for x in declared_kp if x in seen or seen.add(x)]
        if dup:
            issues.append(_issue("reference", f"{kp_field} 重复引用知识点 ID：{dup}"))
        if allowed_kp_ids is not None:
            issues.extend(validate_ids(declared_kp, allowed_kp_ids, kp_field))

    declared_task = payload.get(task_field)
    if isinstance(declared_task, list):
        seen_t: set = set()
        dup_t = [x for x in declared_task if x in seen_t or seen_t.add(x)]
        if dup_t:
            issues.append(_issue("reference", f"{task_field} 重复引用任务 ID：{dup_t}"))
        if allowed_task_ids is not None:
            issues.extend(validate_ids(declared_task, allowed_task_ids, task_field))

    item_kp = _collect_ids(items, "kp_id")
    if isinstance(declared_kp, list) and item_kp:
        missing = [x for x in item_kp if x not in set(declared_kp)]
        if missing:
            issues.append(
                _issue("reference", f"{items_field}[].kp_id 未被 {kp_field} 覆盖：{missing}")
            )

    item_task = _collect_ids(items, "task_id")
    if isinstance(declared_task, list) and item_task:
        declared_set = set(declared_task)
        actual_set = set(item_task)
        absent = sorted(actual_set - declared_set, key=str)
        phantom = sorted(declared_set - actual_set, key=str)
        if absent:
            issues.append(_issue("reference", f"{task_field} 缺少 items 中实际出现的任务 ID：{absent}"))
        if phantom:
            issues.append(_issue("reference", f"{task_field} 声明了 items 中不存在的任务 ID：{phantom}"))

    return issues


def validate_rule_consistency(
    payload: Dict,
    tiers_base_minutes: Optional[int] = None,
    exam_date: Optional[date] = None,
    today: Optional[date] = None,
    mastery_baseline: Optional[Dict[Any, float]] = None,
    duration_field: str = "duration_min",
    date_field: str = "date",
    items_field: str = "items",
) -> List[Dict]:
    """规则一致性：AI 建议不得违反程序规则（时长档位 / 日期窗口 / 掌握度步长）。"""
    issues: List[Dict] = []
    items = payload.get(items_field) if isinstance(payload.get(items_field), list) else [payload]

    if tiers_base_minutes is not None:
        tiers = rules.task_tiers(tiers_base_minutes)
        allowed = {tiers["standard"], tiers["lite"], tiers["minimal"]}
        low, high = min(allowed), max(allowed)
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            minutes = item.get(duration_field)
            if minutes is None:
                continue
            if not isinstance(minutes, (int, float)):
                issues.append(_issue("rule", f"items[{index}].{duration_field} 不是数值"))
            elif minutes < low or minutes > high:
                issues.append(
                    _issue(
                        "rule",
                        f"items[{index}].{duration_field}={minutes} 超出 task_tiers 允许档位范围 [{low}, {high}]",
                    )
                )

    day_floor = today or date.today()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        raw = item.get(date_field)
        if raw is None:
            continue
        parsed = _as_date(raw)
        if parsed is None:
            issues.append(_issue("rule", f"items[{index}].{date_field} 不是合法日期：{raw}"))
            continue
        if parsed < day_floor:
            issues.append(
                _issue("rule", f"items[{index}].{date_field}={parsed.isoformat()} 早于当天 {day_floor.isoformat()}")
            )
        if exam_date is not None and parsed > exam_date:
            issues.append(
                _issue("rule", f"items[{index}].{date_field}={parsed.isoformat()} 晚于考试日 {exam_date.isoformat()}")
            )

    if mastery_baseline:
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            key = item.get("kp_id")
            claimed = item.get("mastery")
            if key is None or claimed is None or key not in mastery_baseline:
                continue
            if not isinstance(claimed, (int, float)):
                issues.append(_issue("rule", f"items[{index}].mastery 不是数值"))
                continue
            base = mastery_baseline[key]
            drift = abs(claimed - base)
            if drift > rules.MASTERY_MAX_STEP:
                issues.append(
                    _issue(
                        "rule",
                        f"items[{index}] 掌握度 {claimed} 相对规则值 {base} 偏差 {drift:.4f} 超过 MASTERY_MAX_STEP={rules.MASTERY_MAX_STEP}",
                    )
                )

    return issues


def validate(
    payload: Any,
    required: Iterable[str] = (),
    enums: Optional[Dict[str, Iterable[str]]] = None,
    id_fields: Optional[Dict[str, Iterable[Any]]] = None,
    numeric_ranges: Optional[Dict[str, tuple]] = None,
    text_fields: Iterable[str] = (),
    reference: Optional[Dict[str, Any]] = None,
    rule: Optional[Dict[str, Any]] = None,
) -> Dict:
    """返回分层校验结果；调用方据 passed 决定展示、修复或规则兜底。

    reference / rule 两层为可选：不传对应参数时该层不执行，也不会出现在 checked_layers 中。
    """
    issues: List[Dict] = []
    checked: List[str] = ["structure"]
    issues.extend(validate_json_shape(payload, required))
    if isinstance(payload, dict):
        # 空容器（如 enums={}）沿用旧行为：仍算执行过该层，只是不产生 issue。
        if enums is not None:
            checked.append("enum")
            for name, allowed in enums.items():
                issues.extend(validate_enum(payload.get(name), allowed, name))
        if id_fields is not None:
            checked.append("id")
            for name, allowed in id_fields.items():
                value = payload.get(name)
                ids = value if isinstance(value, list) else ([value] if value is not None else [])
                issues.extend(validate_ids(ids, allowed, name))
        if numeric_ranges is not None:
            checked.append("numeric")
            for name, bounds in numeric_ranges.items():
                low, high = bounds
                issues.extend(validate_number(payload.get(name), low, high, name))
        # 空 dict {} 表示"用默认字段名执行该层"，因此只判 None 不判真假。
        if reference is not None:
            checked.append("reference")
            issues.extend(validate_reference(payload, **reference))
        if rule is not None:
            checked.append("rule")
            issues.extend(validate_rule_consistency(payload, **rule))
        if text_fields:
            checked.extend(["content", "security"])
            for name in text_fields:
                issues.extend(scan_text(payload.get(name)))
    layers = sorted({item["layer"] for item in issues})
    return {
        "passed": not issues,
        "issues": issues,
        "failed_layers": layers,
        "checked_layers": checked,
        "version": VERSION,
    }


def repair_once(payload: Any, required: Iterable[str] = ()) -> Dict:
    """修复一次：补齐缺失的结构字段（不编造业务数值），返回修复后对象与是否修复。"""
    if not isinstance(payload, dict):
        return {"repaired": False, "payload": payload}
    repaired = dict(payload)
    added = []
    for key in required:
        if key not in repaired:
            repaired[key] = [] if key.endswith("s") else ""
            added.append(key)
    return {"repaired": bool(added), "payload": repaired, "added_fields": added}