"""Bounded contractor-oriented interpretation of contract clauses by local Qwen.

The model determines meaning and drafts professional language. Exact source text,
identities, persistence and all numeric/date arithmetic remain deterministic.
"""

# ruff: noqa: E501, RUF001 -- Russian product prompts are intentionally literal.

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure, _complete

CONTRACT_ANALYSIS_PROFILE = "qwen-contract-analysis-v8"
CONTRACT_ANALYSIS_CONTRACT = "contract-analysis-candidate@1.0.0"
_CLAUSE_CATEGORIES = frozenset(
    {
        "scope",
        "customer_obligation",
        "contractor_obligation",
        "deadline",
        "payment",
        "price",
        "acceptance",
        "liability",
        "warranty",
        "change_procedure",
        "termination",
        "security",
        "insurance",
        "documentation",
        "other",
    }
)
_RISK_KINDS = frozenset(
    {
        "payment_dependency",
        "uncontrolled_obligation",
        "unclear_acceptance",
        "unpaid_change",
        "deadline_exposure",
        "one_sided_liability",
        "excessive_warranty",
        "unlimited_liability",
        "asymmetric_termination",
        "missing_price_adjustment",
        "customer_input_dependency",
        "open_ended_documentation",
        "project_contract_conflict",
        "other_contract_risk",
    }
)
_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
_RISK_MECHANISMS = frozenset(
    {
        "customer_controlled_payment",
        "customer_controlled_acceptance",
        "customer_controlled_deadline",
        "unbounded_scope",
        "unbounded_duration",
        "contractor_bears_customer_cause",
        "asymmetric_remedy",
        "uncontrolled_third_party_dependency",
        "project_facts_conflict",
        "other_explicit_exposure",
    }
)
_SPLITTABLE_BATCH_FAILURES = frozenset(
    {
        "qwen_semantic_response_output_exhausted",
        "qwen_contract_clause_source_not_exact",
        "qwen_contract_risk_invalid",
        "qwen_contract_risk_controller_not_grounded",
        "qwen_contract_risk_revision_invalid",
    }
)
_CUSTOMER_CONTROLLED_MECHANISMS = frozenset(
    {
        "customer_controlled_payment",
        "customer_controlled_acceptance",
        "customer_controlled_deadline",
        "contractor_bears_customer_cause",
    }
)
_CUSTOMER_TERMS = ("заказчик", "customer", "client", "employer")
_EARLY_PERFORMANCE_TERMS = ("досроч", "early performance", "early completion")
_UNVERIFIED_LEGAL_AUTHORITY_ASSERTION = re.compile(
    r"(?:противореч\w*\s+(?:закону|законодательств\w*|(?:правов\w*\s+)?принцип\w*|стать\w*|норм\w*)|"
    r"(?:исключа|отменя)\w*.{0,50}(?:применени\w*\s+)?(?:правов\w*\s+)?принцип\w*|"
    r"(?:являет\w*|услови\w*)\s+(?:незакон\w*|недействительн\w*|ничтожн\w*)|"
    r"наруша\w*\s+(?:закон\w*|законодательств\w*|стать\w*|норм\w*)|"
    r"(?:illegal|unlawful|invalid|unenforceable|contrary to (?:law|statute|legal principle)|"
    r"violates? (?:the )?(?:law|statute|legal principle)))",
    flags=re.IGNORECASE,
)
_MUTUAL_AGREEMENT_TERMS = (
    "по согласованию с подрядчиком",
    "по соглашению сторон",
    "by agreement with the contractor",
    "by mutual agreement",
)
_ORDINARY_PAYMENT_DENIAL_TERMS = (
    "не подлежит оплате",
    "не подлежат оплате",
    "оплате не подлежит",
    "оплате не подлежат",
    "оплата не производится",
    "отказ в оплате",
    "not payable",
    "payment shall not be made",
)
_CHANGED_WORK_PAYMENT_EXPOSURE = re.compile(
    r"(?:дополнительн\w*.{0,35}работ|измененн\w*.{0,35}работ|"
    r"изменени\w*.{0,20}объ[её]м\w*.{0,20}работ|"
    r"превыс\w*.{0,30}объ[её]м\w*.{0,30}работ|"
    r"несогласованн\w*.{0,30}работ|"
    r"(?:additional|changed|varied).{0,35}work|"
    r"excess\w*.{0,30}(?:quantity|volume).{0,30}work)",
    flags=re.IGNORECASE,
)
_NUMERIC_CONTRACT_TERM = re.compile(
    r"(?<![\w])\d+(?:[.,]\d+)*(?:\s*(?:%|процент\w*|percent\w*))?",
    flags=re.IGNORECASE,
)
_RETURN_TERMS = ("возвращ", "return", "refund", "release")
_CONTRACTUAL_FIXED_TERM = re.compile(
    r"(?:в установленн\w*.{0,60}срок|срок\w*.{0,40}(?:установлен|предусмотрен)\w*"
    r".{0,25}(?:договор|пункт)|"
    r"within (?:the )?.{0,40}(?:period|term).{0,30}(?:set|established|specified).{0,30}"
    r"(?:contract|agreement))",
    flags=re.IGNORECASE,
)
_CUSTOMER_CONTROL_ACTION = re.compile(
    r"(?:заказчик\w*.{0,80}(?:устанавлива|определя|утвержда|изменя|назнача|"
    r"согласов|задерж|переда|предоставля|подписыва)|"
    r"(?:установлен|определен|утвержден|изменен|назначен|согласован|подписан)\w*.{0,40}"
    r"заказчик(?:ом|ем)|(?:customer|client|employer).{0,80}(?:sets?|determines?|approves?|"
    r"changes?|appoints?|controls?|delays?|provides?|signs?)|"
    r"(?:set|determined|approved|changed|appointed|controlled|delayed|provided|signed)"
    r".{0,40}by (?:the )?(?:customer|client|employer))",
    flags=re.IGNORECASE,
)


class QwenContractAnalyzer:
    """Analyze one bounded exact-source contract context through local Qwen."""

    def __init__(self, endpoint: str, *, timeout_seconds: float = 900.0) -> None:
        if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("qwen_contract_analysis_endpoint_invalid")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def analyze(self, fragments: Iterable[Mapping[str, object]]) -> dict[str, object]:
        values = [dict(item) for item in fragments]
        if not 1 <= len(values) <= 32:
            raise QwenSemanticFailure("qwen_contract_analysis_batch_size_invalid")
        try:
            parsed = self._analyze_once(values)
        except QwenSemanticFailure as exc:
            if exc.code not in _SPLITTABLE_BATCH_FAILURES or len(values) < 2:
                raise
            midpoint = len(values) // 2
            parsed = _merge_contract_analysis_parts(
                self.analyze(values[:midpoint]),
                self.analyze(values[midpoint:]),
            )
        result: dict[str, object] = {
            "contract": CONTRACT_ANALYSIS_CONTRACT,
            "profile_version": CONTRACT_ANALYSIS_PROFILE,
            **parsed,
        }
        result["result_digest"] = semantic_digest(result)
        return result

    def _analyze_once(self, values: list[dict[str, object]]) -> dict[str, object]:
        allowed: dict[str, str] = {}
        prompt_rows: list[dict[str, object]] = []
        total_chars = 0
        for item in values:
            locator_id = str(item.get("source_locator_id") or "")
            text = " ".join(str(item.get("text") or "").split())
            if not locator_id or not text or locator_id in allowed:
                raise QwenSemanticFailure("qwen_contract_analysis_input_invalid")
            total_chars += len(text)
            if total_chars > 12_000:
                raise QwenSemanticFailure("qwen_contract_analysis_context_too_large")
            allowed[locator_id] = text
            prompt_rows.append(
                {
                    "source_locator_id": locator_id,
                    "page": item.get("page"),
                    "text": text,
                }
            )
        prompt = _prompt(prompt_rows)
        output_tokens = _contract_output_token_budget(total_chars)
        raw = _complete(
            self._endpoint,
            prompt,
            self._timeout_seconds,
            max_tokens=output_tokens,
        )
        try:
            parsed = parse_contract_analysis(raw, allowed_text_by_locator=allowed)
        except QwenSemanticFailure as exc:
            if not exc.code.startswith("qwen_contract_"):
                raise
            repaired = _complete(
                self._endpoint,
                _repair_prompt(prompt_rows, raw, exc.code),
                self._timeout_seconds,
                max_tokens=output_tokens,
            )
            parsed = parse_contract_analysis(repaired, allowed_text_by_locator=allowed)
        return parsed


def parse_contract_analysis(
    raw: str, *, allowed_text_by_locator: Mapping[str, str]
) -> dict[str, object]:
    """Validate model JSON against exact bounded input identities and source text."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_contract_analysis_invalid_json") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("clauses"), list):
        raise QwenSemanticFailure("qwen_contract_analysis_invalid_shape")
    clauses: list[dict[str, object]] = []
    seen_clause_ids: set[str] = set()
    for index, raw_clause in enumerate(payload["clauses"], start=1):
        if not isinstance(raw_clause, dict):
            raise QwenSemanticFailure("qwen_contract_clause_invalid")
        clause_ref = str(raw_clause.get("clause_ref") or f"batch-{index}").strip()
        locator_ids = raw_clause.get("source_locator_ids")
        source_text = " ".join(str(raw_clause.get("source_text") or "").split())
        category = str(raw_clause.get("category") or "")
        if (
            not clause_ref
            or clause_ref in seen_clause_ids
            or not isinstance(locator_ids, list)
            or not locator_ids
            or category not in _CLAUSE_CATEGORIES
        ):
            raise QwenSemanticFailure("qwen_contract_clause_invalid")
        normalized_locators = [str(value) for value in locator_ids]
        if any(value not in allowed_text_by_locator for value in normalized_locators):
            raise QwenSemanticFailure("qwen_contract_clause_evidence_invalid")
        allowed_source = " ".join(allowed_text_by_locator[value] for value in normalized_locators)
        exact_source_text = _resolve_grounded_clause_source(source_text, allowed_source)
        if exact_source_text is None:
            raise QwenSemanticFailure("qwen_contract_clause_source_not_exact")
        seen_clause_ids.add(clause_ref)
        clauses.append(
            {
                "clause_ref": clause_ref,
                "section": _optional_text(raw_clause.get("section")),
                "source_text": exact_source_text,
                "source_locator_ids": normalized_locators,
                "category": category,
                "customer_obligation": _optional_text(raw_clause.get("customer_obligation")),
                "contractor_obligation": _optional_text(raw_clause.get("contractor_obligation")),
                "condition": _optional_text(raw_clause.get("condition")),
            }
        )
    risks_raw = payload.get("risks", [])
    if not isinstance(risks_raw, list):
        raise QwenSemanticFailure("qwen_contract_risks_invalid")
    risks: list[dict[str, object]] = []
    disagreement_clause_refs: set[str] = set()
    source_text_by_clause = {str(item["clause_ref"]): str(item["source_text"]) for item in clauses}
    for raw_risk in risks_raw:
        if not isinstance(raw_risk, dict):
            raise QwenSemanticFailure("qwen_contract_risk_invalid")
        clause_ref = str(raw_risk.get("clause_ref") or "")
        kind = str(raw_risk.get("kind") or "")
        severity = str(raw_risk.get("severity") or "")
        confidence = raw_risk.get("confidence")
        basis = str(raw_risk.get("basis") or "")
        risk_mechanism = str(raw_risk.get("risk_mechanism") or "")
        trigger_text = " ".join(str(raw_risk.get("trigger_text") or "").split())
        adverse_effect_text = " ".join(str(raw_risk.get("adverse_effect_text") or "").split())
        if (
            clause_ref not in seen_clause_ids
            or kind not in _RISK_KINDS
            or severity not in _SEVERITIES
            or basis != "explicit_clause_text"
            or risk_mechanism not in _RISK_MECHANISMS
            or not trigger_text
            or trigger_text.casefold() not in source_text_by_clause[clause_ref].casefold()
            or not adverse_effect_text
            or adverse_effect_text.casefold() not in source_text_by_clause[clause_ref].casefold()
            or not isinstance(confidence, (int, float))
            or not 0 <= float(confidence) <= 1
        ):
            raise QwenSemanticFailure("qwen_contract_risk_invalid")
        description = contract_commercial_narrative_without_unverified_authority(
            raw_risk.get("description")
        )
        practical_consequence = contract_commercial_narrative_without_unverified_authority(
            raw_risk.get("practical_consequence")
        )
        recommended_action = contract_commercial_narrative_without_unverified_authority(
            raw_risk.get("recommended_action")
        )
        if not description or not practical_consequence or not recommended_action:
            raise QwenSemanticFailure("qwen_contract_risk_invalid")
        if not contract_risk_controller_is_grounded(
            {
                "kind": kind,
                "risk_mechanism": risk_mechanism,
                "trigger_text": trigger_text,
                "adverse_effect_text": adverse_effect_text,
            }
        ):
            raise QwenSemanticFailure("qwen_contract_risk_controller_not_grounded")
        disagreement = raw_risk.get("disagreement_required")
        proposed = _optional_text(raw_risk.get("proposed_contractor_wording"))
        uncertainty = _optional_text(raw_risk.get("uncertainty"))
        replacement_source_text = _optional_text(raw_risk.get("replacement_source_text"))
        exact_replacement_source = (
            _resolve_exact_source_quote(
                replacement_source_text or "", source_text_by_clause[clause_ref]
            )
            if replacement_source_text
            else None
        )
        if (
            not isinstance(disagreement, bool)
            or (disagreement and (not proposed or exact_replacement_source is None))
            or (disagreement and clause_ref in disagreement_clause_refs)
        ):
            raise QwenSemanticFailure("qwen_contract_risk_revision_invalid")
        if disagreement and not contract_proposed_wording_is_grounded(
            exact_replacement_source or "", proposed or ""
        ):
            # Preserve the exact-source commercial risk but do not publish a
            # negotiation proposal containing a new amount, percentage or
            # deadline invented outside the admitted clause.
            disagreement = False
            proposed = None
            exact_replacement_source = None
            uncertainty = uncertainty or "PROPOSED_WORDING_NUMERIC_TERM_UNGROUNDED"
        if disagreement:
            disagreement_clause_refs.add(clause_ref)
        risks.append(
            {
                "clause_ref": clause_ref,
                "kind": kind,
                "basis": basis,
                "risk_mechanism": risk_mechanism,
                "trigger_text": trigger_text,
                "adverse_effect_text": adverse_effect_text,
                "severity": severity,
                "description": description,
                "practical_consequence": practical_consequence,
                "recommended_action": recommended_action,
                "proposed_contractor_wording": proposed,
                "replacement_source_text": exact_replacement_source,
                "disagreement_required": disagreement,
                "confidence": float(confidence),
                "uncertainty": uncertainty,
                "authority": "contract_commercial_risk",
            }
        )
    return {"clauses": clauses, "risks": risks}


def _contract_output_token_budget(total_chars: int) -> int:
    """Scale strict-JSON capacity with bounded source size, never without limit."""

    if total_chars < 0:
        raise ValueError("contract_context_size_invalid")
    return max(1_800, min(5_000, 1_200 + total_chars // 2))


def _optional_text(value: object) -> str | None:
    normalized = " ".join(str(value or "").split())
    return normalized or None


def contract_commercial_narrative_without_unverified_authority(
    value: object,
) -> str | None:
    """Remove unsupported legal conclusions from commercial contract review.

    Contract risk analysis is useful without claiming that a clause is illegal,
    invalid or contrary to a legal principle. Verified legal conclusions belong
    to a separately qualified authority path. Keep the remaining practical
    sentences exactly as model-authored apart from whitespace normalization.
    """

    normalized = _optional_text(value)
    if normalized is None:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    qualified = [
        sentence
        for sentence in sentences
        if sentence and not _UNVERIFIED_LEGAL_AUTHORITY_ASSERTION.search(sentence)
    ]
    result = " ".join(qualified).strip()
    return result or None


def _mentions_customer(value: str) -> bool:
    folded = value.casefold()
    return any(term in folded for term in _CUSTOMER_TERMS)


def contract_risk_controller_is_grounded(risk: Mapping[str, object]) -> bool:
    """Reject a Customer-controlled mechanism without an explicit Customer actor."""

    mechanism = str(risk.get("risk_mechanism") or "")
    combined = " ".join(
        (
            str(risk.get("trigger_text") or ""),
            str(risk.get("adverse_effect_text") or ""),
        )
    ).casefold()
    if str(risk.get("kind") or "") == "unpaid_change" and not (
        _CHANGED_WORK_PAYMENT_EXPOSURE.search(combined)
        and any(term in combined for term in _ORDINARY_PAYMENT_DENIAL_TERMS)
    ):
        # This professional category is reserved for an exact combination of
        # changed/additional/excess work scope and an explicit payment denial.
        # Restitution, termination, warranty and other cost clauses must use
        # their own risk kind even when they have a financial consequence.
        return False
    if (
        str(risk.get("kind") or "") == "customer_input_dependency"
        and mechanism == "customer_controlled_payment"
        and any(term in combined for term in _RETURN_TERMS)
        and _CONTRACTUAL_FIXED_TERM.search(combined)
        and not any(term in combined for term in _ORDINARY_PAYMENT_DENIAL_TERMS)
    ):
        # A return or release tied to a term already fixed elsewhere in the
        # contract does not itself establish Customer discretion or delay.
        # A bounded clause cannot become a risk solely by assuming breach of
        # that deadline.
        return False
    if (
        mechanism == "customer_controlled_payment"
        and any(term in combined for term in _EARLY_PERFORMANCE_TERMS)
        and any(term in combined for term in _MUTUAL_AGREEMENT_TERMS)
        and not any(term in combined for term in _ORDINARY_PAYMENT_DENIAL_TERMS)
    ):
        # An optional route for accepting or paying early performance by
        # mutual agreement does not restrict the ordinary payment obligation.
        # Treating it as a payment dependency invents an adverse effect that
        # the selected wording does not establish.
        return False
    if mechanism not in _CUSTOMER_CONTROLLED_MECHANISMS:
        return True
    if not _mentions_customer(combined):
        return False
    if mechanism in {"customer_controlled_acceptance", "customer_controlled_deadline"}:
        return bool(_CUSTOMER_CONTROL_ACTION.search(combined))
    return True


def contract_proposed_wording_is_grounded(source_text: str, proposed_text: str) -> bool:
    """Reject new numeric commercial terms absent from the clause being replaced."""

    def terms(value: str) -> set[str]:
        return {
            "".join(match.group(0).casefold().split()).replace(",", ".")
            for match in _NUMERIC_CONTRACT_TERM.finditer(value)
        }

    return terms(proposed_text).issubset(terms(source_text))


_SOURCE_QUOTE_TRANSLATION = str.maketrans(
    {
        "«": '"',
        "»": '"',
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "−": "-",
    }
)


def _resolve_exact_source_quote(candidate: str, allowed_source: str) -> str | None:
    """Resolve harmless typography variants back to the admitted exact text.

    Qwen may replace a typographic quote or dash while otherwise copying a
    clause verbatim. The one-character translation keeps offsets stable, so a
    successful match is persisted as the original admitted source slice. Any
    lexical change or paraphrase remains rejected.
    """

    if not candidate:
        return None
    folded_candidate = (
        unicodedata.normalize("NFC", candidate).translate(_SOURCE_QUOTE_TRANSLATION).lower()
    )
    folded_source = (
        unicodedata.normalize("NFC", allowed_source).translate(_SOURCE_QUOTE_TRANSLATION).lower()
    )
    start = folded_source.find(folded_candidate)
    if start < 0:
        return None
    return allowed_source[start : start + len(candidate)]


def _resolve_grounded_clause_source(candidate: str, allowed_source: str) -> str | None:
    """Return exact admitted text, using bounded locator context when overlap is strong."""

    exact = _resolve_exact_source_quote(candidate, allowed_source)
    if exact is not None:
        return exact
    if not candidate or len(allowed_source) > 3_000:
        return None
    candidate_tokens = _source_tokens(candidate)
    source_tokens = set(_source_tokens(allowed_source))
    if len(candidate_tokens) < 4:
        return None
    overlap = sum(token in source_tokens for token in candidate_tokens) / len(candidate_tokens)
    return allowed_source if overlap >= 0.8 else None


def _source_tokens(value: str) -> list[str]:
    folded = unicodedata.normalize("NFC", value).translate(_SOURCE_QUOTE_TRANSLATION).casefold()
    return re.findall(r"[\w]+", folded, flags=re.UNICODE)


def _merge_contract_analysis_parts(
    *parts: Mapping[str, object],
) -> dict[str, object]:
    """Merge recursively split model results without conflating clause identities."""

    clauses: list[dict[str, object]] = []
    risks: list[dict[str, object]] = []
    used_refs: set[str] = set()
    for part_index, part in enumerate(parts, start=1):
        ref_map: dict[str, str] = {}
        raw_clauses = part.get("clauses")
        for raw_clause in raw_clauses if isinstance(raw_clauses, list | tuple) else ():
            if not isinstance(raw_clause, Mapping):
                continue
            clause = dict(raw_clause)
            old_ref = str(clause.get("clause_ref") or "")
            new_ref = old_ref
            suffix = 1
            while new_ref in used_refs:
                suffix += 1
                new_ref = f"{old_ref} [{part_index}.{suffix}]"
            clause["clause_ref"] = new_ref
            used_refs.add(new_ref)
            ref_map[old_ref] = new_ref
            clauses.append(clause)
        raw_risks = part.get("risks")
        for raw_risk in raw_risks if isinstance(raw_risks, list | tuple) else ():
            if not isinstance(raw_risk, Mapping):
                continue
            risk = dict(raw_risk)
            old_ref = str(risk.get("clause_ref") or "")
            risk["clause_ref"] = ref_map.get(old_ref, old_ref)
            risks.append(risk)
    return {"clauses": clauses, "risks": risks}


def _prompt(rows: list[dict[str, object]]) -> str:
    return f"""Ты анализируешь ограниченный фрагмент договора строительного подряда с позиции коммерческих рисков Подрядчика.
Источник истины — только CONTEXT. Не придумывай пункты, цифры, сроки, нормы права или факты проекта.
Выдели самостоятельные условия договора. source_text должен быть дословной непрерывной цитатой из одного или нескольких указанных фрагментов (нормализация пробелов допустима).
Оценивай практический риск: исполнимость обязательства, зависимость оплаты/приёмки от Заказчика, изменение объёмов и РД, сроки, ответственность, гарантию, расторжение и исходные данные.
Обычные сбалансированные условия не отмечай как риск. Не выдавай коммерческую оценку за подтверждённое юридическое заключение.
Не приписывай Заказчику подписание акта, согласование, задержку или иное управляющее действие, если точная запускающая формулировка или точное неблагоприятное последствие прямо не называют Заказчика (Customer/Client/Employer). Само требование оформить или подписать акт не доказывает зависимость от Заказчика. Не предлагай перенос ответственности за качество работ на Заказчика как автоматическое последствие задержки документа или подписи.
Обязанность вернуть объективно излишне выплаченную сумму, устранить завышение фактического объёма или исключить несогласованный материал/способ выполнения не является риском сама по себе. Не придумывай, какой именно орган скрывается за словами «контрольный орган», и не называй его внутренним органом Заказчика, СРО или иным лицом без прямого текста. Не требуй решения суда как единственно допустимого подтверждения, если исходный пункт не даёт Заказчику одностороннее и неоспоримое право самому установить нарушение. Вид unpaid_change применяй только к прямо сформулированному риску неоплаты дополнительной/изменённой работы, а не к возврату установленной переплаты.
Возможность досрочной приёмки или оплаты досрочно выполненных работ по соглашению Сторон и при наличии финансирования не ограничивает обычную оплату сама по себе. Не отмечай такой дополнительный добровольный механизм как риск, если точный текст не отменяет, не задерживает и не ставит под условие оплату работ, выполненных в обычные сроки.
Не отмечай риск только потому, что условие возлагает на Подрядчика обычную обязанность по исправлению дефектов, допущенных Подрядчиком; передаёт Заказчику более длительную гарантию производителя; требует установленный законом способ или ограниченный срок обеспечения; либо автоматически следует обязательному изменению закона. Для риска должна быть прямо сформулированная управленческая причина: зависимость от решения/действия Заказчика, неограниченный объём или срок, ответственность за причину вне контроля Подрядчика, односторонняя мера без проверяемого ограничения, либо явный конфликт с фактами проекта.
Короткий срок, установленный самому Заказчику для передачи площадки, документов, согласования или иного действия, не является риском Подрядчика сам по себе: не предполагай заранее, что Заказчик нарушит свою обязанность. Обычное право направить требование о неустойке за нарушение обязательств, прямо предусмотренных договором, не является неограниченной ответственностью без отдельной формулировки о неограниченном или несоразмерном последствии. Односторонний акт контроля не является самостоятельным риском, если данный фрагмент только требует направить его Подрядчику и не устанавливает для него неблагоприятное последствие. Расходы Подрядчика на вскрытие или исправление, прямо вызванные его собственным нарушением обязанности предъявить работы или устранить свой дефект, являются обычной ответственностью и не отмечаются как риск, если условие не распространяет расходы на случаи надлежащего исполнения Подрядчиком.
Возврат или уменьшение обеспечения в срок, прямо установленный этим договором или указанным пунктом договора, не является риском только потому, что действие выполняет Заказчик. Не предполагай нарушение установленного срока без прямой неблагоприятной формулировки.
CONTEXT является ограниченной частью документа. Отсутствие реквизита, условия или значения в CONTEXT не доказывает его отсутствие во всём договоре. Не формируй риск только на основании того, что продолжение таблицы, пункта, раздела или приложения не попало в CONTEXT. Этот этап принимает только риск, который прямо создаётся формулировкой условия в CONTEXT. Отсутствующий во всём договоре механизм проверяется отдельным итоговым этапом после анализа всех частей.
Для каждого риска basis должен быть только explicit_clause_text. trigger_text — дословная непрерывная цитата формулировки, запускающей риск. adverse_effect_text — дословная непрерывная цитата из того же source_text, которая прямо устанавливает неблагоприятное последствие, обязанность, зависимость или меру для Подрядчика. Если неблагоприятное последствие можно только предположить из возможного будущего нарушения Заказчиком, не добавляй риск. Число, объём или цена сами по себе не доказывают отсутствие порядка их изменения. Если точных trigger_text и adverse_effect_text нет, не добавляй риск.
Если нужна редакция Подрядчика, она должна быть конкретной и соответствовать исходному пункту. Не вводи новую сумму, процент, количество дней или иной числовой порог, которого нет в заменяемом source_text; используй ненумерованное проверяемое условие или оставь proposed_contractor_wording=null и disagreement_required=false.
Для disagreement_required=true укажи replacement_source_text: дословный непрерывный фрагмент source_text, который полностью заменяется proposed_contractor_wording. Если один пункт содержит несколько связанных рисков, верни один объединённый риск и одну согласованную редакцию этого пункта; не создавай две замены одного clause_ref.

Верни только JSON:
{{"clauses":[{{"clause_ref":"номер или локальная метка","section":"раздел или null","source_text":"точная цитата","source_locator_ids":["id"],"category":"scope|customer_obligation|contractor_obligation|deadline|payment|price|acceptance|liability|warranty|change_procedure|termination|security|insurance|documentation|other","customer_obligation":"... или null","contractor_obligation":"... или null","condition":"... или null"}}],"risks":[{{"clause_ref":"ссылка на clause_ref","kind":"payment_dependency|uncontrolled_obligation|unclear_acceptance|unpaid_change|deadline_exposure|one_sided_liability|excessive_warranty|unlimited_liability|asymmetric_termination|missing_price_adjustment|customer_input_dependency|open_ended_documentation|project_contract_conflict|other_contract_risk","basis":"explicit_clause_text","risk_mechanism":"customer_controlled_payment|customer_controlled_acceptance|customer_controlled_deadline|unbounded_scope|unbounded_duration|contractor_bears_customer_cause|asymmetric_remedy|uncontrolled_third_party_dependency|project_facts_conflict|other_explicit_exposure","trigger_text":"точная запускающая формулировка из source_text","adverse_effect_text":"точная формулировка неблагоприятного последствия для Подрядчика из source_text","severity":"low|medium|high|critical","description":"что неясно или опасно","practical_consequence":"практическое последствие для Подрядчика","recommended_action":"что уточнить или изменить","replacement_source_text":"точный заменяемый фрагмент source_text или null","proposed_contractor_wording":"конкретная редакция или null","disagreement_required":true,"confidence":0.0,"uncertainty":"... или null"}}]}}

CONTEXT:
{json.dumps(rows, ensure_ascii=False, separators=(",", ":"))}
"""


def _repair_prompt(rows: list[dict[str, object]], invalid: str, failure_code: str) -> str:
    return (
        _prompt(rows)
        + "\nПредыдущий ответ отклонён валидатором: "
        + failure_code
        + ". Исправь только JSON и ссылки на предоставленные source_locator_id. "
        + "Не добавляй новых фактов.\nINVALID_RESPONSE:\n"
        + invalid[:12_000]
    )
