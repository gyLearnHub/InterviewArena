from __future__ import annotations

import re
from typing import Any

DIRECT_KEYS = {
    "name",
    "full_name",
    "real_name",
    "username",
    "姓名",
    "名字",
    "真实姓名",
    "phone",
    "mobile",
    "telephone",
    "tel",
    "手机号",
    "手机",
    "电话",
    "email",
    "邮箱",
    "address",
    "home_address",
    "residential_address",
    "地址",
    "住址",
    "家庭住址",
    "现住址",
    "居住地",
    "id_card",
    "id_card_number",
    "identity_number",
    "national_id",
    "身份证",
    "身份证号",
    "证件号码",
    "wechat",
    "wechat_id",
    "weixin",
    "wx",
    "微信",
    "微信号",
    "qq",
    "qq_number",
    "qq号",
    "bank_card",
    "bank_card_number",
    "银行卡",
    "银行卡号",
    "passport",
    "passport_number",
    "护照",
    "护照号",
    "birth_date",
    "birthday",
    "date_of_birth",
    "出生日期",
    "出生年月",
    "github",
    "github_url",
    "linkedin",
    "linkedin_url",
    "personal_website",
    "portfolio_url",
    "个人主页",
    "作品集链接",
}
INTERNAL_ID_KEYS = {
    "id",
    "user_id",
    "interview_id",
    "round_id",
    "question_id",
    "resume_id",
    "trace_id",
    "checkpoint_id",
    "parent_question_id",
    "regenerated_from_question_id",
}
CATEGORY_KEYS = {
    "company",
    "company_name",
    "employer",
    "公司",
    "school",
    "school_name",
    "university",
    "学校",
}
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
LANDLINE_RE = re.compile(r"(?<!\d)(?:0\d{2,3}[- ]?)?\d{7,8}(?!\d)")
ID_CARD_RE = re.compile(
    r"(?<![0-9A-Z])(?:\d{6}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])"
    r"(?:0[1-9]|[12]\d|3[01])\d{3}[0-9X]|\d{15})(?![0-9A-Z])",
    re.IGNORECASE,
)
PASSPORT_RE = re.compile(r"(?<![A-Z0-9])(?:[EGP]\d{8}|[A-Z]{2}\d{7})(?![A-Z0-9])", re.IGNORECASE)
BANK_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")
WECHAT_RE = re.compile(
    r"(?i)(?:(?:微信|wechat|weixin|wx)\s*(?:号|id)?\s*[:：]?\s*)"
    r"[a-z][-_a-z0-9]{5,19}"
)
QQ_RE = re.compile(r"(?i)(?:qq\s*(?:号)?\s*[:：]?\s*)[1-9]\d{4,11}")
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\]\[()，。；;]+")
SELF_NAME_RE = re.compile(
    r"(?P<prefix>我叫|我的名字(?:叫|是)|姓名(?:叫|是|为)|名字(?:叫|是|为))"
    r"\s*(?P<value>[\u3400-\u9fff·]{2,8})"
)
ADDRESS_RE = re.compile(
    r"(?P<prefix>家庭住址|现住址|居住地址|联系地址|住址|地址|居住地|住在|现居|家住|住)"
    r"\s*[:：]?\s*(?P<value>[\u3400-\u9fffA-Za-z0-9\-号弄栋单元室路街巷区县市省镇乡村]{4,80})"
)
SENSITIVE_TEXT_PATTERNS = (
    EMAIL_RE,
    PHONE_RE,
    ID_CARD_RE,
    PASSPORT_RE,
    BANK_CARD_RE,
    WECHAT_RE,
    QQ_RE,
    URL_RE,
    SELF_NAME_RE,
    ADDRESS_RE,
)


def anonymize_payload(value: Any) -> Any:
    direct_values: set[str] = set()
    category_values: dict[str, str] = {}
    _collect_sensitive_values(value, direct_values, category_values)
    anonymized = _anonymize(value, direct_values, category_values)
    if contains_direct_identifier(anonymized):
        raise ValueError("payload still contains a direct identifier after anonymization")
    return anonymized


def _anonymize(
    value: Any,
    direct_values: set[str],
    category_values: dict[str, str],
) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = key.strip().casefold()
            if normalized in DIRECT_KEYS:
                result[key] = "[REDACTED]"
            elif normalized in INTERNAL_ID_KEYS:
                result[key] = 0
            elif normalized in CATEGORY_KEYS:
                result[key] = _category_label(normalized)
            else:
                result[key] = _anonymize(item, direct_values, category_values)
        return result
    if isinstance(value, list):
        return [_anonymize(item, direct_values, category_values) for item in value]
    if isinstance(value, tuple):
        return [_anonymize(item, direct_values, category_values) for item in value]
    if isinstance(value, str):
        return _scrub_text(value, direct_values, category_values)
    return value


def contains_direct_identifier(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            direct_key = str(key).strip().casefold() in DIRECT_KEYS
            if direct_key and item is not None and item not in ("", "[REDACTED]"):
                return True
            if contains_direct_identifier(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(contains_direct_identifier(item) for item in value)
    if isinstance(value, str):
        return any(pattern.search(value) is not None for pattern in SENSITIVE_TEXT_PATTERNS)
    return False


def _scrub_text(
    value: str,
    direct_values: set[str],
    category_values: dict[str, str],
) -> str:
    result = EMAIL_RE.sub("[EMAIL]", value)
    result = PHONE_RE.sub("[PHONE]", result)
    result = ID_CARD_RE.sub("[ID_CARD]", result)
    result = PASSPORT_RE.sub("[PASSPORT]", result)
    result = BANK_CARD_RE.sub("[BANK_CARD]", result)
    result = WECHAT_RE.sub("[WECHAT]", result)
    result = QQ_RE.sub("[QQ]", result)
    result = URL_RE.sub("[URL]", result)
    result = SELF_NAME_RE.sub(lambda match: f"{match.group('prefix')}[REDACTED]", result)
    result = ADDRESS_RE.sub(lambda match: f"{match.group('prefix')}[ADDRESS]", result)
    result = LANDLINE_RE.sub("[PHONE]", result)
    replacements = {
        **{item: "[REDACTED]" for item in direct_values},
        **category_values,
    }
    for sensitive, replacement in sorted(
        replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        result = result.replace(sensitive, replacement)
    return result


def _collect_sensitive_values(
    value: Any,
    direct_values: set[str],
    category_values: dict[str, str],
) -> None:
    if isinstance(value, dict):
        for raw_key, item in value.items():
            normalized = str(raw_key).strip().casefold()
            if normalized in DIRECT_KEYS:
                direct_values.update(_leaf_strings(item))
            elif normalized in CATEGORY_KEYS:
                replacement = _category_label(normalized)
                for text in _leaf_strings(item):
                    category_values[text] = replacement
            _collect_sensitive_values(item, direct_values, category_values)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_sensitive_values(item, direct_values, category_values)


def _leaf_strings(value: Any) -> set[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return {stripped} if len(stripped) >= 2 else set()
    if isinstance(value, dict):
        return {
            text
            for item in value.values()
            for text in _leaf_strings(item)
        }
    if isinstance(value, (list, tuple)):
        return {text for item in value for text in _leaf_strings(item)}
    return set()


def _category_label(key: str) -> str:
    is_school = "school" in key or "university" in key or key == "学校"
    return "[SCHOOL]" if is_school else "[COMPANY]"
