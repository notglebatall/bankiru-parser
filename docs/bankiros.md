# Историческое описание Bankiros

Ниже сохранено описание прежнего парсера Bankiros. Оно не относится к текущему механическому парсеру Banki.ru.

Проект предназначен для сбора, нормализации и контроля качества данных по ставкам банковских вкладов и накопительных счетов. 
MVP ограничен одним источником данных - Bankiros.

Каталог `bankiros_parser/` содержит архивный исследовательский скрипт и старые выгрузки. Текущий парсер находится в `src/parser.py`.

## Цель MVP

Собрать воспроизводимый парсер Bankiros, который:

- получает список вкладов и накопительных счетов;
- скачивает страницы отдельных продуктов;
- сохраняет сырые HTML-снимки;
- извлекает условия продукта и таблицы ставок;
- приводит данные к единой схеме;
- валидирует результат;
- сохраняет нормализованную выгрузку и отчет о качестве.

## Схема работы

```text
Запуск парсера
  -> загрузка страниц каталога Bankiros
    -> извлечение ссылок на продукты
      -> загрузка страниц вкладов и накопительных счетов
        -> сохранение сырых HTML-снимков
          -> извлечение данных продукта и таблицы ставок
            -> нормализация названий, сумм, сроков и ставок
              -> проверка качества и полноты данных
                -> сохранение CSV / XLSX выгрузки
                -> сохранение отчета о запуске и ошибках
```

## Схема парсинга Bankiros

На этапе MVP каталог Bankiros обходится по страницам:

```text
https://bankiros.ru/deposit?page=1
https://bankiros.ru/deposit?page=2
https://bankiros.ru/deposit?page=3
https://bankiros.ru/deposit?page=4
```

Последовательность:

1. Скачать страницы каталога `page=1..4`.
2. Извлечь из каталога ссылки на продукты и регномера банков, если они доступны в карточке.
3. Удалить дубли по паре `source_url + bank_regn`.
4. Скачать страницу каждого продукта.
5. Сохранить сырой HTML продукта в `data/raw/<run_id>/`.
6. Найти на странице RUB-таблицу ставок.
7. Распарсить диапазоны сроков из заголовков таблицы.
8. Распарсить диапазоны сумм из строк таблицы.
9. Распарсить значения ставок из ячеек.
10. Развернуть матрицу ставок в плоские строки.
11. Нормализовать и провалидировать результат.
12. Сохранить выгрузку и отчет о качестве.

## Единица данных

Одна строка итоговой выгрузки соответствует одной комбинации:

```text
банк + продукт + валюта + диапазон суммы + диапазон срока + ставка
```

Базовая схема строки:

```text
run_id
source
bank_name
bank_regn
product_name
product_type
currency
min_amount
max_amount
min_days
max_days
rate
replenishment
partial_withdrawal
prolongation
source_url
parsed_at
raw_snapshot_id
```

## Структура БД

Для MVP используется компактная схема из справочников, истории запусков, строк ставок, сырых снимков и ошибок парсинга.

```text
banks
  1 -> many products

products
  1 -> many rate_rows

parse_runs
  1 -> many rate_rows
  1 -> many raw_snapshots
  1 -> many parse_errors

raw_snapshots
  1 -> many rate_rows
  1 -> many parse_errors
```

### banks

Справочник банков. Основной стабильный идентификатор - регномер банка, если он доступен.

```text
id
name
normalized_name
regn
source
source_bank_url
created_at
updated_at
```

Рекомендуемые ограничения:

```text
unique(regn)
unique(source, normalized_name)
```

### products

Справочник банковских продуктов, найденных на Bankiros.

```text
id
bank_id
source
source_url
name
product_type
created_at
updated_at
```

`product_type`:

```text
deposit
savings_account
```

Рекомендуемая уникальность:

```text
unique(source, source_url)
```

### parse_runs

История запусков парсера.

```text
id
source
status
started_at
finished_at
catalogue_pages_from
catalogue_pages_to
found_products
fetched_products
parsed_products
failed_products
output_rows
error_message
created_at
```

`status`:

```text
running
success
partial_success
failed
```

### rate_rows

Основная таблица нормализованных ставок. Одна строка соответствует одной комбинации продукта, суммы, срока и ставки.

```text
id
run_id
bank_id
product_id
source
bank_regn
bank_name
product_name
product_type
currency
min_amount
max_amount
min_days
max_days
rate
replenishment
partial_withdrawal
prolongation
source_url
raw_snapshot_id
parsed_at
created_at
```

Рекомендуемые типы:

```text
rate: numeric(6, 3)
min_amount: numeric(18, 2)
max_amount: numeric(18, 2), nullable
min_days: integer
max_days: integer, nullable
```

Верхние границы без ограничения хранятся как `NULL`, а не как искусственные значения `9999` или `999999999`.

### raw_snapshots

Сырые HTML-снимки каталога и страниц продуктов. HTML хранится файлом, в БД хранится путь и hash.

```text
id
run_id
source
source_url
snapshot_type
http_status
content_hash
storage_path
fetched_at
created_at
```

`snapshot_type`:

```text
catalogue
product
```

Пример хранения файлов:

```text
data/raw/<run_id>/<content_hash>.html
```

### parse_errors

Ошибки скачивания, парсинга и валидации. Ошибка одной страницы не должна прерывать весь запуск.

```text
id
run_id
source
source_url
bank_regn
product_name_hint
error_type
error_message
raw_snapshot_id
created_at
```

Примеры `error_type`:

```text
request_failed
product_link_not_found
title_parse_failed
rub_table_not_found
rate_table_parse_failed
validation_failed
```

## Принципы реализации

- Не изменять старый исследовательский скрипт без отдельной задачи.
- Сохранять сырые данные каждого запуска для повторной проверки.
- Использовать строгую схему данных и валидацию перед экспортом.
- Отдельно фиксировать ошибки парсинга, а не прерывать весь запуск из-за одной страницы.
- Делать парсер детерминированным: понятные таймауты, retry, логи и отчет по итогам запуска.
