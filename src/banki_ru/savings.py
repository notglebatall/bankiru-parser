import json

from datetime import datetime, timezone
from decimal import Decimal
from math import ceil

from html.parser import HTMLParser
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen


SOURCE_URL = "https://www.banki.ru/products/deposits/?type=14&special%5B%5D=14"


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


# Находит в HTML исходные данные каталога накопительных счетов
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
    raise ValueError("Не найдены данные блока «Все предложения» накопительных счетов")


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


# Обрабатывает каждую плашку накопительного счёта и возвращает словарь с данными
def _offer_row(offer: dict, collected_at: str) -> dict:
    effective = offer.get("efficient_rate")
    bonus = offer.get("action_percent") if offer.get("is_action_active") else None
    displayed = None
    if effective is not None:
        displayed = float(Decimal(str(effective)) + Decimal(str(bonus or 0)))
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
        "product_url": urljoin(SOURCE_URL, offer.get("product_url") or ""),
        "product_id": offer.get("id"),
        "bank_id": offer.get("bank_id"),
    }


# Точка входа: собирает все накопительные счета и возвращает список словарей с данными
def collect_savings() -> list[dict]:
    html, _ = _get(SOURCE_URL)
    data = _initial_data(html)
    initial = data["defaultOffersResults"]
    expected_banks = int(initial["banksCount"])
    expected_offers = int(initial["totalCount"])
    per_page = int(data["defaultFormData"]["per_page"])
    if not initial["results"] or min(expected_banks, expected_offers, per_page) < 1:
        raise ValueError("В каталоге не найдены накопительные счета")

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
    if any(not offer.get("is_saving_account") for offer in offers):
        raise ValueError("В выдаче накопительных счетов найдены вклады")

    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return [_offer_row(offer, collected_at) for offer in offers]
