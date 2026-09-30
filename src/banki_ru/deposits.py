import json

from datetime import datetime, timezone
from decimal import Decimal
from math import ceil

from html.parser import HTMLParser
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen


SOURCE_URL = "https://www.banki.ru/products/deposits/"


class ModuleParser(HTMLParser):
    # Подготавливает список для найденных настроек модулей
    def __init__(self):
        super().__init__()
        self.options = []

    # Собирает значения data-module-options из тегов div.
    def handle_starttag(self, tag, attrs):
        if tag == "div":
            for name, value in attrs:
                if name == "data-module-options" and value:
                    self.options.append(value)


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "li", "p", "div"}:
            self.parts.append(" ")

    def handle_data(self, data):
        self.parts.append(data)


def _plain_text(html: str | None) -> str | None:
    if not html:
        return None
    parser = TextParser()
    parser.feed(html)
    return " ".join("".join(parser.parts).split()) or None


def _values(items: dict | list | None) -> list:
    return list(items.values()) if isinstance(items, dict) else list(items or [])


# Находит в HTML исходные данные каталога вкладов
def _initial_data(html: str) -> dict:
    parser = ModuleParser()
    parser.feed(html)

    for option in parser.options:
        try:
            data = json.loads(option)
        except json.JSONDecodeError:
            continue
        if data.get("pageType") == "MAINPRODUCT_SEARCH" and "defaultOffersResults" in data:
            return data
    raise ValueError("Не найдены данные блока «Все предложения»")


# Загружает URL и возвращает текст ответа и итоговый адрес.
def _get(url: str) -> tuple[str, str]:
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": SOURCE_URL,
    })
    with urlopen(request, timeout=30) as response:
        text = response.read().decode(response.headers.get_content_charset() or "utf-8")
        return text, response.geturl()


# Строит URL API для указанной страницы каталога.
def _page_url(data: dict, page: int) -> str:
    form = data["defaultFormData"]
    query = []

    for key, value in form.items():
        if isinstance(value, list):
            query.extend((f"{key}[]", item) for item in value)
        elif value is not None:
            query.append((key, value))

    query.extend(data["defaultSort"].items())
    query.extend((
        ("page", page),
        ("page_type", data["pageType"]),
        ("isMobileApp", "false"),
        ("aff_sub2", "/products/deposits/"),
        ("is_main_page", 1),
    ))

    city = quote(form["city"], safe="")
    return urljoin(SOURCE_URL, f"api/group/{city}/") + "?" + urlencode(query)


# Обрабатывает каждую плашку вклада и возвращает словарь с данными
def _offer_row(offer: dict, collected_at: str) -> dict:
    effective = offer.get("efficient_rate")
    bonus = offer.get("action_percent") if offer.get("is_action_active") else None
    displayed = None
    if effective is not None:
        displayed = float(Decimal(str(effective)) + Decimal(str(bonus or 0)))
    badges = []
    if offer.get("is_new_money"):
        badges.append("Новые деньги")
    if offer.get("is_new_client"):
        badges.append("Новый клиент")
    badges.extend(tag["name"] for tag in offer.get("tags") or [])
    return {
        "collected_at_utc": collected_at,
        "bank_name": offer.get("bank_name"),
        "bank_licence": offer.get("bank_licence"),
        "product_name": offer.get("product_name"),
        "displayed_rate": displayed,
        "effective_rate": effective,
        "nominal_rate_min": offer.get("rate_min"),
        "nominal_rate_max": offer.get("rate_max"),
        "bonus_rate": bonus,
        "period_from_days": offer.get("period_from"),
        "period_to_days": offer.get("period_to"),
        "amount_from": offer.get("amount_from"),
        "amount_to": offer.get("amount_to"),
        "currency": offer.get("currency_code"),
        "replenishment_possible": offer.get("is_replenishment_possible"),
        "replenishment_conditions": _plain_text(offer.get("replenishment_comment_html")),
        "replenishment_restrictions": _values(offer.get("replenishment_restriction_list")),
        "partial_withdrawal_possible": offer.get("is_partial_withdrawal_possible"),
        "partial_withdrawal_conditions": _plain_text(offer.get("partial_withdrawal_comment_html")),
        "partial_withdrawal_restrictions": _values(offer.get("partial_withdrawal_restriction_list")),
        "prolongation_possible": offer.get("is_prolongation_possible"),
        "prolongation_conditions": (
            offer.get("prolongation_comment") or _plain_text(offer.get("prolongation_comment_html"))
        ),
        "prolongation_max": offer.get("prolongation_max"),
        "capitalization": (offer.get("capitalization") or {}).get("name"),
        "interest_payment_periods": _values(offer.get("payment_period_list")),
        "early_termination": (offer.get("early_termination_method") or {}).get("name"),
        "online_opening_possible": offer.get("is_online_opening_possible"),
        "new_money": offer.get("is_new_money"),
        "new_money_comment": offer.get("new_money_comment"),
        "new_client": offer.get("is_new_client"),
        "new_client_comment": offer.get("new_client_comment"),
        "badges": badges,
        "product_url": urljoin(SOURCE_URL, offer.get("product_url") or ""),
        "product_id": offer.get("id"),
        "bank_id": offer.get("bank_id"),
    }


# Точка входа: собирает все предложения вкладов и возвращает список словарей с данными
def collect_deposits() -> list[dict]:
    html, _ = _get(SOURCE_URL)
    data = _initial_data(html)
    initial = data["defaultOffersResults"]
    expected_banks = int(initial["banksCount"])
    expected_offers = int(initial["totalCount"])
    per_page = int(data["defaultFormData"]["per_page"])
    if not initial["results"] or min(expected_banks, expected_offers, per_page) < 1:
        raise ValueError("В каталоге не найдены предложения вкладов")

    groups = list(initial["results"])
    for page in range(2, ceil(expected_banks / per_page) + 1):
        body, _ = _get(_page_url(data, page))
        result = json.loads(body)
        if (result.get("page") != page or result.get("total") != expected_banks
                or result.get("items_count") != expected_offers):
            raise ValueError(f"Изменились счётчики каталога на странице {page}")
        groups.extend(result["grouped_table"])

    bank_ids = [group["id"] for group in groups]
    offers = [offer for group in groups for offer in group["deposit_result_rows"]]

    if len(groups) != expected_banks or len(set(bank_ids)) != expected_banks:
        raise ValueError(f"Собрано {len(groups)} из {expected_banks} банков или найдены повторы")
    if len(offers) != expected_offers:
        raise ValueError(f"Собрано {len(offers)} из {expected_offers} предложений")

    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return [
        _offer_row(offer, collected_at)
        for offer in offers
        if not offer.get("is_saving_account")
    ]
