import base64
import json
import re
import time

from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from bs4 import BeautifulSoup
from tqdm.auto import tqdm


SOURCE_URL = "https://bankiros.ru/deposit/moskva?from=mainpage"
USER_AGENTS_PATH = Path(__file__).resolve().with_name("userAgents.json")


# Берёт desktop User-Agent с наиболее новой версией Chrome из соседнего файла.
def _headers() -> dict:
    agents = json.loads(USER_AGENTS_PATH.read_text(encoding="utf-8"))
    desktop = [agent for agent in agents
               if re.match(r"Mozilla/5\.0 \((?:Windows|Macintosh|X11)", agent) and "Chrome/" in agent
               and not any(word in agent for word in ("Mobile", "Android", "iPhone", "iPad", "Xbox", "XBOX", "bot"))]
    if not desktop:
        raise ValueError(f"В {USER_AGENTS_PATH} не найден desktop User-Agent Chrome")
    agent = max(desktop, key=lambda value: int(re.search(r"Chrome/(\d+)", value)[1]))
    return {
        "User-Agent": agent,
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": SOURCE_URL,
    }


def _get(opener, url: str, headers: dict, *, ajax: bool = False) -> str:
    if urlsplit(url).netloc != "bankiros.ru":
        raise ValueError(f"Неожиданный адрес Bankiros: {url}")
    request_headers = dict(headers)
    if ajax:
        request_headers["X-Requested-With"] = "XMLHttpRequest"
    with opener.open(Request(url, headers=request_headers), timeout=30) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8")


def _text(node) -> str | None:
    return node.get_text(" ", strip=True) if node is not None else None


# Не придумывает отсутствующие границы и сохраняет исходный текст в записи.
def _bounds(text: str | None) -> tuple:
    if not text or any(word in text.lower() for word in ("бессрочно", "не ограничена")):
        return None, None
    # Перечисление сроков: границы описывают крайние варианты, исходный список
    # сохраняется в period_text и не означает доступность каждого дня между ними.
    if re.fullmatch(r"\d+(?:(?:\s*,\s+|\s+(?:или|и)\s+)\d+)+\s*(?:дн\.?|дней|дня|день)",
                    text.strip(), flags=re.IGNORECASE):
        days = [int(value) for value in re.findall(r"\d+", text)]
        return min(days), max(days)
    compact = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    values = [float(value.replace(",", ".")) for value in re.findall(r"\d+(?:[.,]\d+)?", compact)]
    values = [int(value) if value.is_integer() else value for value in values]
    if len(values) == 2:
        return tuple(values)
    if len(values) == 1:
        if text.lower().startswith("от "):
            return values[0], None
        if text.lower().startswith("до "):
            return None, values[0]
        return values[0], values[0]
    raise ValueError(f"Не удалось разобрать диапазон: {text}")


def _rate(text: str | None) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text or "")
    return float(match[1].replace(",", ".")) if match else None


# Читает и видимые, и скрытые до раскрытия предложения из основного списка.
def _catalog(html: str, collected_at: str) -> tuple[list[dict], list[str], int, int, int]:
    soup = BeautifulSoup(html, "html.parser")
    catalog = soup.select_one("#products_list")
    counter = soup.select_one('[data-js="filter-count"]')
    if catalog is None or counter is None:
        raise ValueError("Не найден каталог Bankiros или счётчик предложений")
    rows = []
    for card in catalog.select(".xxx-table-list__row-inner"):
        product = card.select_one("[data-product_id][data-url]")
        name = card.select_one(".xxx-table-list__cell--name a")
        logo = card.select_one(".xxx-table-list__cell--bank img")
        currency = card.select_one(".xxx-table-list__cell--sum meta[content]")
        if any(node is None for node in (product, name, logo, currency)):
            raise ValueError("Изменилась структура карточки Bankiros")
        term_node = card.select_one(".xxx-table-list__cell--term .xxx-font-size-18")
        amount_node = card.select_one(".xxx-table-list__cell--sum .xxx-accent-text")
        rate_node = card.select_one(".xxx-table-list__cell--stavka .xxx-table-list__accent-text")
        period_text, amount_text, rate_text = _text(term_node), _text(amount_node), _text(rate_node)
        if not period_text or not amount_text or _rate(rate_text) is None:
            raise ValueError(f"Не найдены ставка, срок или сумма: {product['data-url']}")
        period_from, period_to = _bounds(period_text)
        amount_from, amount_to = _bounds(amount_text)
        licence = re.search(r"Лиц\.\s*№\s*(\d+)", card.get_text(" ", strip=True))
        rows.append({
            "collected_at_utc": collected_at,
            "bank_name": logo.get("alt"),
            "bank_licence": licence[1] if licence else None,
            "product_name": name.get_text(" ", strip=True),
            "displayed_rate": _rate(rate_text),
            "displayed_rate_text": rate_text,
            "period_from_days": period_from,
            "period_to_days": period_to,
            "period_text": period_text,
            "amount_from": amount_from,
            "amount_to": amount_to,
            "amount_text": amount_text,
            "currency": currency["content"].upper(),
            "is_saving_account": card.select_one(".funded") is not None,
            "badges": [_text(label) for label in card.select(".xxx-table-list__label")],
            "product_id": int(product["data-product_id"]),
            "product_url": urljoin(SOURCE_URL, product["data-url"]),
        })
    pagination = soup.select_one("#product-list-pagination")
    pages = json.loads(base64.b64decode(pagination["data-urls"])) if pagination else []
    pages = [urljoin(SOURCE_URL, page) for page in pages]
    group_count = len(catalog.select("tr[data-key]"))
    expected_groups = int(pagination["data-total-count"]) if pagination else group_count
    if not rows:
        raise ValueError("В каталоге Bankiros не найдены предложения")
    return rows, pages, int(counter.get_text(strip=True)), expected_groups, group_count


def _conditions(soup) -> dict:
    conditions = {}
    for cell in soup.select("#info2 .xxx-products-page__tab-cell, #info3 .xxx-products-page__tab-cell"):
        title = cell.select_one(".xxx-products-page__tab-title")
        if title is not None:
            label = title.get_text(" ", strip=True)
            value = " ".join(_text(child) or str(child).strip()
                             for child in cell.contents if child is not title)
            conditions[label] = " ".join(value.split())
        for item in cell.select("li.xxx-g-list__item"):
            label, separator, value = item.get_text(" ", strip=True).partition(":")
            if separator:
                conditions[label.strip()] = value.strip()
    return conditions


# Сохраняет все валюты и исходные заголовки: столбцы могут обозначать периоды
# начисления процентов, а не варианты срока открытия вклада.
def _details(html: str, row: dict) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("h1") is None or soup.select_one("#info2") is None:
        raise ValueError("Не найдены условия продукта Bankiros")
    currencies = {item["data-tab"].lstrip("."): _text(item)
                  for item in soup.select(".change_currency_item[data-tab]")}
    rate_rows = []
    for wrapper in soup.select(".xxx-switched-rate-table"):
        currency = next((currencies[cls] for cls in wrapper.get("class", []) if cls in currencies), None)
        table = wrapper.select_one("table")
        if table is None or not currency:
            raise ValueError("Не найдена таблица ставок или её валюта")
        headings = [_text(cell) for cell in table.select("thead tr td, thead tr th")][1:]
        for table_row in table.select("tbody tr"):
            cells = table_row.find_all(["td", "th"], recursive=False)
            if len(cells) != len(headings) + 1:
                raise ValueError("Изменилась структура таблицы ставок")
            amount_text = _text(cells[0])
            for period_text, cell in zip(headings, cells[1:]):
                # Мобильная подпись содержит срок, который нельзя принять за ставку.
                for caption in cell.select(".xxx-table-default__emphasize"):
                    caption.decompose()
                rate_text = _text(cell)
                rate_rows.append({
                    "currency": currency,
                    "amount_text": amount_text,
                    "period_text": period_text,
                    "rate": _rate(rate_text),
                    "rate_text": rate_text,
                })
    if not rate_rows:
        raise ValueError("Не найдена подробная таблица ставок")
    conditions = _conditions(soup)
    rates = [item["rate"] for item in rate_rows
             if item["currency"] == row["currency"] and item["rate"] is not None]
    if not rates:
        raise ValueError(f"Не найдены ставки в валюте {row['currency']}")
    row.update({
        "nominal_rate_min": min(rates),
        "nominal_rate_max": max(rates),
        "rate_rows": rate_rows,
        "conditions": conditions,
        "additional_conditions": _text(soup.select_one("#info4")),
        "capitalization": conditions.get("Капитализация процентов"),
        "interest_payment_periods": conditions.get("Выплата процентов"),
        "early_termination": conditions.get("Досрочное расторжение"),
        "online_opening_possible": True if any(
            _text(item) == "Открытие онлайн"
            for item in soup.select(".xxx-products-page__brief-info li")
        ) else None,
    })
    # JSON-LD содержит границы суммы, которых нет в краткой карточке.
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict) or item.get("@type") != "DepositAccount":
                continue
            amount = item.get("amount") or {}
            if str(amount.get("currency", "")).upper() == row["currency"]:
                row["amount_from"] = amount.get("minValue", row["amount_from"])
                row["amount_to"] = amount.get("maxValue", row["amount_to"])
    for field, label in (("replenishment", "Пополнение счета"),
                         ("partial_withdrawal", "Частичное снятие"),
                         ("prolongation", "Пролонгация")):
        value = conditions.get(label)
        row[field + "_conditions"] = value
        row[field + "_possible"] = {"Есть": True, "Нет": False}.get(value)
    # Срок открытия берётся из условий, а не из периодов начисления таблицы.
    term = conditions.get("Срок вклада")
    if term and ("дн" in term or "день" in term or "бессрочно" in term):
        row["period_from_days"], row["period_to_days"] = _bounds(term)
        row["period_text"] = term
    return row


def collect_deposits(*, include_savings: bool = False, details: bool = True,
                     progress: bool = True) -> list[dict]:
    """Собирает московский каталог; details=False отключает запросы к продуктам.

    По умолчанию возвращает вклады. include_savings=True включает накопительные
    счета; они отмечены is_saving_account. Ошибки не превращаются в пустой результат.
    progress=False скрывает индикаторы загрузки каталога и условий продуктов.
    """
    headers = _headers()
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with tqdm(total=None, desc="Bankiros: каталог", unit="стр.", disable=not progress) as bar:
        first_html = _get(opener, SOURCE_URL, headers)
        rows, pages, expected, expected_groups, group_count = _catalog(first_html, collected_at)
        bar.reset(total=len(pages) + 1)
        bar.update(1)
        for page in pages:
            time.sleep(0.2)
            html = _get(opener, page, headers, ajax=True)
            more, _, count, groups, page_groups = _catalog(html, collected_at)
            if count != expected or groups != expected_groups:
                raise ValueError(f"Изменились счётчики каталога: {page}")
            rows.extend(more)
            group_count += page_groups
            bar.update(1)
    if (len(rows) != expected or len({row['product_id'] for row in rows}) != expected
            or group_count != expected_groups):
        raise ValueError(f"Собрано {len(rows)} из {expected} предложений; найдены повторы или пропуски")
    rows = [row for row in rows if include_savings or not row["is_saving_account"]]
    if details:
        with tqdm(total=len(rows), desc="Bankiros: условия", unit="вклад", disable=not progress) as bar:
            for row in rows:
                bar.set_postfix_str(row["bank_name"] or "")
                time.sleep(0.2)
                try:
                    _details(_get(opener, row["product_url"], headers), row)
                except Exception as error:
                    raise ValueError(f"Не удалось собрать условия {row['product_url']}: {error}") from error
                bar.update(1)
    return rows
