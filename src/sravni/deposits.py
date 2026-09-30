import json
import re
import time

from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


SOURCE_URL = "https://www.sravni.ru/vklady/"
API_URL = "https://www.sravni.ru/proxy-deposits/deposits"


def _get(url: str, payload: dict | None = None) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": SOURCE_URL,
    }
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    with urlopen(Request(url, data=body, headers=headers), timeout=30) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8")


def _query(html: str, endpoint: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None:
        raise ValueError("Не найдены исходные данные Сравни")
    state = json.loads(script.get_text())["props"]["initialReduxState"]
    queries = state["api"]["queries"].values()
    for query in queries:
        if query.get("endpointName") == endpoint and query.get("status") == "fulfilled":
            return query
    raise ValueError(f"Не найдены данные Сравни: {endpoint}")


def _plain_text(html: str | None) -> str | None:
    if not html:
        return None
    if "<" not in html:
        return html.strip() or None
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True) or None


def _offer_row(offer: dict, filters: dict, collected_at: str) -> dict:
    bank, product = offer["bankDetail"], offer["product"]
    rate = next(item for item in product["details"] if item["type"] == "rate")
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", rate["displayValue"])
    if match is None or product.get("depositType") not in {"deposit", "accumulative"}:
        raise ValueError(f"Не удалось разобрать карточку Сравни: {product['id']}")
    tags = offer.get("tags") or []
    return {
        "collected_at_utc": collected_at,
        "bank_name": bank["bankName"],
        "bank_licence": None,
        "bank_id": bank["bankId"],
        "product_name": product["name"],
        "product_id": product["id"],
        "product_url": f"https://www.sravni.ru/bank/{bank['alias']}/vklad/{product['alias']}/",
        "bank_product_url": product.get("linkToProduct"),
        "displayed_rate": float(match[1].replace(",", ".")),
        "displayed_rate_text": rate["displayValue"],
        "rate_explanation": _plain_text(rate.get("tooltip")),
        "period_from_days": None,
        "period_to_days": None,
        "amount_from": None,
        "amount_to": None,
        "currency": filters["currency"].upper(),
        "calculation_amount": filters["amount"],
        "seed_period_days": product.get("seedPeriodDays"),
        "is_saving_account": product["depositType"] == "accumulative",
        "online_opening_possible": True if any(tag["type"] == "online" for tag in tags) else None,
        "badges": [tag["displayValue"] for tag in tags],
        "card_details": product["details"],
    }


def _details(html: str, row: dict) -> dict:
    query = _query(html, "updateDeposit")
    data = query["data"]
    if data["productId"] != row["product_id"]:
        raise ValueError("Открыт другой продукт Сравни")
    conditions, descriptions = {}, {}
    for group in data.get("relatedInformation") or []:
        for item in group["info"]:
            label = item["displayTitle"]
            conditions[label] = _plain_text(item.get("displayValue"))
            description = _plain_text(item.get("description"))
            if description:
                descriptions[label] = description
    # terms содержит доходность для расчётной суммы и условий клиента,
    # а не полную таблицу номинальных ставок по всем суммам.
    terms = data.get("terms") or []
    days = [item["period"]["daysValue"] for item in terms
            if item["period"].get("daysValue") is not None]
    row.update({
        "bank_licence": conditions.get("Лицензия"),
        "amount_from": (data.get("minAmount") or {}).get("amount"),
        "amount_to": (data.get("maxAmount") or {}).get("amount"),
        "period_from_days": min(days) if days and not row["is_saving_account"] else None,
        "period_to_days": max(days) if days and not row["is_saving_account"] else None,
        "rate_rows": [{
            "currency": (data.get("amount") or {}).get("currency", "").upper(),
            "calculation_amount": (data.get("amount") or {}).get("amount"),
            "period_days": term["period"].get("daysValue"),
            "period_text": term["period"].get("displayValue"),
            "rate": term["annualRate"].get("value"),
            "rate_text": term["annualRate"].get("displayValue"),
            "selected": term.get("selected"),
            "unavailable": term.get("unavailable"),
        } for term in terms],
        "conditions": conditions,
        "condition_descriptions": descriptions,
        "capitalization": conditions.get("Капитализация"),
        "interest_payment_periods": conditions.get("Выплата процентов"),
        "early_termination": conditions.get("Досрочное закрытие"),
        "client_types": data.get("clientTypes") or [],
        "interest_payments": data.get("interestPayments") or [],
        "features": data.get("features") or [],
        "best_rate": data.get("bestRate"),
        "detail_calculation_filters": query["originalArgs"]["filters"],
    })
    for field, label in (
        ("replenishment", "Пополнение"),
        ("partial_withdrawal", "Частичное снятие"),
        ("prolongation", "Автопролонгация"),
    ):
        value = conditions.get(label)
        row[field + "_conditions"] = value
        row[field + "_possible"] = {"да": True, "нет": False}.get((value or "").lower())
    return row


def collect_deposits(*, include_savings: bool = False, details: bool = True) -> list[dict]:
    """Собирает каталог с фильтрами страницы, по умолчанию только вклады.

    Продукты маркетплейса Сравни пропускаются.
    details=False отключает отдельные запросы к условиям продуктов.
    """
    initial = _query(_get(SOURCE_URL), "deposits")
    result, filters = initial["data"], initial["originalArgs"]
    expected = int(result["total"])
    if expected < 1 or not result["data"]:
        raise ValueError("В каталоге Сравни не найдены предложения")
    # API принимает limit всего каталога; offset и page не листают выдачу.
    if len(result["data"]) < expected:
        result = json.loads(_get(API_URL, {**filters, "limit": expected}))
    offers = result["data"]
    if (result["total"] != expected or len(offers) != expected
            or len({offer["product"]["id"] for offer in offers}) != expected):
        raise ValueError(f"Собрано {len(offers)} из {expected} предложений; повторы или пропуски")
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [_offer_row(offer, filters, collected_at) for offer in offers
            if not offer["product"].get("fromMarketPlace")]
    rows = [row for row in rows if include_savings or not row["is_saving_account"]]
    if details:
        for row in rows:
            time.sleep(0.2)
            url = row["product_url"] + "?" + urlencode({"amount": filters["amount"]})
            try:
                _details(_get(url), row)
            except Exception as error:
                raise ValueError(f"Не удалось собрать условия {url}: {error}") from error
    return rows
