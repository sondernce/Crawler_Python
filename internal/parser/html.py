"""CSS-парсинг, regex fallback и фильтрация данных."""

import re
from typing import List, Dict
from bs4 import BeautifulSoup, Tag
from internal.config.dsl import ExtractRule, Filters

# Стандартный email + защищенные форматы
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
EMAIL_REGEX_PROTECTED = re.compile(r"[a-zA-Z0-9._%+\-]+\s*\(?at\)?\s*[a-zA-Z0-9.\-]+\s*\(?dot\)?\s*[a-zA-Z]{2,}", re.IGNORECASE)
# Стандартный российский номер: +7 (XXX) XXX-XX-XX
PHONE_REGEX_STD = re.compile(r"(?:\+7|8|7)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")
# Компактный: +7XXXXXXXXXX / 8XXXXXXXXXX (ровно 3+7 цифр, как в Go)
PHONE_REGEX_COMPACT = re.compile(r"(?:\+7|8|7)\(?\d{3}\)?\d{7}")
# Международные номера
PHONE_REGEX_WIDE = re.compile(r"\+\d[\d\s\-\(\)]{7,20}")

# Стоп-слова для фильтрации
STOP_WORDS = [
    "страница", "преподаватели", "сотрудники", "назад", "меню", "список",
    "отдел", "центр", "лаборатория", "дирекция", "институт", "общежитие",
    "кафедра", "управление", "факультет", "департамент", "бюро", "служба",
    "сектор", "комплекс", "отделение", "филиал", "представительство",
    "карта", "фотография", "кнопка", "реквизиты", "наименование", "организации",
    "магазина", "мессенджеры", "форма", "функция", "филиалы", "почта",
    "видеотрансляция", "разметка", "президент", "кампус", "карьера",
    "программа", "проект", "услуги", "контакты", "адрес", "режим", "работы",
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
    "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
    "сентября", "октября", "ноября", "декабря", "года", "числа",
    "телефон", "email", "e-mail", "mail", "факс", "skype", "telegram", "whatsapp",
    "поиск", "войти", "регистрация", "корзина", "личный", "кабинет", "новости",
    "события", "мероприятия", "конференция", "семинар", "конкурс", "олимпиада",
    "публикации", "статьи", "монография", "диссертация", "учебник", "пособие",
]


def normalize_phone(phone: str) -> str:
    """Приводит номер к читаемому виду, убирая лишние пробелы."""
    phone = phone.strip()
    phone = re.sub(r"\s+", " ", phone)
    return phone


def decode_protected_email(raw: str) -> str:
    """Декодирует защищённые email вида user [at] domain [dot] ru."""
    raw = raw.lower()
    raw = raw.replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
    raw = raw.replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", ".")
    raw = raw.replace(" ", "")
    return raw


def extract_field(element: Tag, selector: str) -> str:
    """Извлекает значение поля из элемента по CSS-селектору."""
    # Разбиваем составной селектор по запятым
    parts = [s.strip() for s in selector.split(",")]
    for part in parts:
        found = element.select_one(part)
        if found is None:
            continue

        # Если элемент — ссылка с mailto: или tel:, извлекаем контакт из href
        href = found.get("href", "")
        if href.startswith("mailto:"):
            return href[len("mailto:"):]
        if href.startswith("tel:"):
            return href[len("tel:"):]

        # data-* атрибуты (как в Go: data-email, data-mail, data-phone, data-tel)
        for attr in ("data-email", "data-mail"):
            val = found.get(attr, "")
            if val:
                return val.strip()
        for attr in ("data-phone", "data-tel"):
            val = found.get(attr, "")
            if val:
                return val.strip()
        aria = found.get("aria-label", "")
        if aria:
            return aria.strip()
        title_val = found.get("title", "")
        if title_val:
            return title_val.strip()

        text = found.get_text(strip=True)
        if text:
            return text
    return ""


def parse_page(soup: BeautifulSoup, rule: ExtractRule) -> List[Dict[str, str]]:
    """Парсит страницу согласно правилу извлечения."""
    results: List[Dict[str, str]] = []

    # Разбиваем составной селектор контейнера по запятым
    container_selectors = [s.strip() for s in rule.selector.split(",")]
    containers = []
    for sel in container_selectors:
        containers.extend(soup.select(sel))

    for container in containers:
        item: Dict[str, str] = {}
        found_any = False

        for field_name, field_selector in rule.fields.items():
            val = extract_field(container, field_selector)
            if val:
                item[field_name] = val
                found_any = True

        if found_any:
            # Regex fallback внутри контейнера
            container_html = str(container)
            if not item.get("email"):
                emails = EMAIL_REGEX.findall(container_html)
                if emails:
                    item["email"] = emails[0].strip()
                else:
                    protected = EMAIL_REGEX_PROTECTED.findall(container_html)
                    if protected:
                        item["email"] = decode_protected_email(protected[0])
            if not item.get("phone"):
                for pattern in (PHONE_REGEX_STD, PHONE_REGEX_COMPACT, PHONE_REGEX_WIDE):
                    phones = pattern.findall(container_html)
                    if phones:
                        item["phone"] = normalize_phone(phones[0])
                        break

            results.append(item)

    return results


def extract_profile_links(soup: BeautifulSoup, rule: ExtractRule) -> List[str]:
    """Извлекает ссылки на персональные страницы из найденных контейнеров."""
    links: List[str] = []
    if not rule.profile_link:
        return links

    container_selectors = [s.strip() for s in rule.selector.split(",")]
    containers = []
    for sel in container_selectors:
        containers.extend(soup.select(sel))

    for container in containers:
        for a in container.select(rule.profile_link):
            href = a.get("href", "")
            if href:
                links.append(href)
    return links


def apply_filters(data: List[Dict[str, str]], filters: Filters) -> List[Dict[str, str]]:
    """Применяет глубокую фильтрацию данных."""
    filtered: List[Dict[str, str]] = []

    for item in data:
        is_valid = True

        # Проверка на стоп-слова
        name = item.get("full_name", "").lower()
        for stop in STOP_WORDS:
            if stop in name:
                is_valid = False
                break
        if not is_valid:
            continue

        # Валидация длины имени
        full_name = item.get("full_name", "")
        if len(full_name) < 5 or len(full_name) > 50:
            continue

        # Проверка ExcludeEmpty
        for field in filters.exclude_empty:
            if not item.get(field, "").strip():
                is_valid = False
                break
        if not is_valid:
            continue

        # Проверка MustContain
        for substr in filters.must_contain:
            found = False
            for val in item.values():
                if substr in val:
                    found = True
                    break
            if not found:
                is_valid = False
                break
        if not is_valid:
            continue

        # Дополнительная проверка email
        email = item.get("email", "")
        if email and "@" not in email:
            continue

        filtered.append(item)

    return filtered


def apply_basic_filters(data: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Применяет минимальную фильтрацию для fallback-результатов (regex)."""
    filtered: List[Dict[str, str]] = []
    seen: Dict[str, bool] = {}

    for item in data:
        key = item.get("email", "") + "|" + item.get("phone", "")
        if seen.get(key):
            continue
        seen[key] = True

        # Проверяем, что email содержит @
        email = item.get("email", "")
        if email and "@" not in email:
            continue

        filtered.append(item)

    return filtered


def _cell_text(cell: Tag) -> str:
    """Извлекает текст из ячейки таблицы, включая mailto/tel из ссылок."""
    # Ищем mailto
    for a in cell.find_all("a", href=True):
        href = a["href"]
        if href.startswith("mailto:"):
            return href[len("mailto:"):]
        if href.startswith("tel:"):
            return href[len("tel:"):]
    return cell.get_text(strip=True)


# Сопоставление русских/английских заголовков столбцов с полями
_TABLE_HEADER_MAP = {
    "full_name": [
        "фио", "руководитель", "директор", "начальник", "сотрудник",
        "преподаватель", "фамилия", "имя", "контактное лицо",
        "представитель", "ф.и.о.", "ф и о", "фамилия инициалы",
        "руководитель структурного подразделения", "фио руководителя",
    ],
    "phone": [
        "телефон", "тел", "phone", "тел.", "контактный телефон",
        "контактные телефоны", "телефоны", "телефон/факс", "факс",
    ],
    "email": [
        "email", "e-mail", "почта", "электронная почта",
        "адрес электронной почты", "адреса электронной почты",
        "e mail", "mail", "e-mail:", "email:",
    ],
}


def _match_header(text: str) -> str:
    """Определяет тип столбца по тексту заголовка. Возвращает имя поля или пустую строку."""
    lowered = text.lower().strip()
    for field, variants in _TABLE_HEADER_MAP.items():
        for variant in variants:
            # Ищем вариант как отдельное слово (с границами слов), чтобы "тел"
            # не срабатывало на "образовательной" или "руководителя"
            pattern = r"(?:^|\W)" + re.escape(variant) + r"(?:\W|$)"
            if re.search(pattern, lowered):
                return field
    return ""


def parse_tables(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Парсит HTML-таблицы, ищет строки с ФИО/телефоном/email."""
    results: List[Dict[str, str]] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Определяем заголовки из первой строки
        header_row = rows[0]
        header_cells = header_row.find_all(["th", "td"])
        if not header_cells:
            continue

        column_map: Dict[int, str] = {}
        for idx, cell in enumerate(header_cells):
            header_text = cell.get_text(strip=True)
            field = _match_header(header_text)
            if field:
                column_map[idx] = field

        if "full_name" not in column_map.values() and "email" not in column_map.values():
            # Таблица без нужных заголовков — пропускаем
            continue

        # Парсим данные
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            item: Dict[str, str] = {}
            for idx, field in column_map.items():
                if idx < len(cells):
                    val = _cell_text(cells[idx])
                    if val:
                        item[field] = val

            if item.get("full_name") or item.get("email"):
                # Regex fallback внутри строки таблицы
                row_html = str(row)
                if not item.get("email"):
                    emails = EMAIL_REGEX.findall(row_html)
                    if emails:
                        item["email"] = emails[0].strip()
                    else:
                        protected = EMAIL_REGEX_PROTECTED.findall(row_html)
                        if protected:
                            item["email"] = decode_protected_email(protected[0])
                if not item.get("phone"):
                    for pattern in (PHONE_REGEX_STD, PHONE_REGEX_COMPACT, PHONE_REGEX_WIDE):
                        phones = pattern.findall(row_html)
                        if phones:
                            item["phone"] = normalize_phone(phones[0])
                            break
                results.append(item)

    return results


def extract_regex_fallback(html: str) -> List[Dict[str, str]]:
    """Ищет email и телефоны напрямую в HTML через regex."""
    results: List[Dict[str, str]] = []

    all_emails = list(EMAIL_REGEX.findall(html))
    for m in EMAIL_REGEX_PROTECTED.findall(html):
        all_emails.append(decode_protected_email(m))

    seen_email: Dict[str, bool] = {}
    seen_phone: Dict[str, bool] = {}

    for email in all_emails:
        email = email.strip()
        if not email or seen_email.get(email):
            continue
        seen_email[email] = True
        results.append({"email": email})

    for pattern in (PHONE_REGEX_STD, PHONE_REGEX_COMPACT):
        phones = pattern.findall(html)
        for phone in phones:
            phone = normalize_phone(phone)
            if not phone or seen_phone.get(phone):
                continue
            seen_phone[phone] = True

            added = False
            for item in results:
                if not item.get("phone"):
                    item["phone"] = phone
                    added = True
                    break
            if not added:
                results.append({"phone": phone})

    return results
