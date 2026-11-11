import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

DEPARTMENTS = {
    "engineering": "開発部",
    "sales": "営業部",
    "corporate": "管理部",
    "design": "デザイン部",
}
STATUSES = {"pending": "確認待ち", "approved": "承認済み", "rejected": "差し戻し"}
KINDS = {"equipment": "備品購入", "training": "研修参加", "remote": "在宅勤務"}
INPUT_FIELDS = ("title", "applicant", "department", "kind", "details")


@dataclass(frozen=True)
class PortalRequest:
    id: int
    title: str
    applicant: str
    department: str
    kind: str
    details: str
    status: str
    created_at: str

    def to_dict(self) -> dict[str, int | str]:
        return {
            "id": self.id,
            "title": self.title,
            "applicant": self.applicant,
            "department": self.department,
            "kind": self.kind,
            "details": self.details,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class NewRequest:
    title: str
    applicant: str
    department: str
    kind: str
    details: str


class InputError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("申請内容を確認してください。")
        self.errors = errors


def validate_new_request(values: Mapping[str, str]) -> NewRequest:
    cleaned = {field: values.get(field, "").strip() for field in INPUT_FIELDS}
    errors: dict[str, str] = {}
    limits = {
        "title": ("件名", 1, 80),
        "applicant": ("申請者名", 1, 40),
        "details": ("申請内容", 10, 1000),
    }
    for field, (label, minimum, maximum) in limits.items():
        value = cleaned[field]
        if not minimum <= len(value) <= maximum:
            errors[field] = f"{label}は{minimum}〜{maximum}文字で入力してください。"
        allowed_controls = "\n\r\t" if field == "details" else ""
        if any(
            unicodedata.category(character) == "Cc" and character not in allowed_controls
            for character in value
        ):
            errors[field] = f"{label}に使用できない文字が含まれています。"
    if cleaned["department"] not in DEPARTMENTS:
        errors["department"] = "担当部署を選択してください。"
    if cleaned["kind"] not in KINDS:
        errors["kind"] = "申請種別を選択してください。"
    if errors:
        raise InputError(errors)
    return NewRequest(**cleaned)
