import re

class RegexEqual(str):
    def __eq__(self, pattern):
        return bool(re.search(pattern, self))
    
    
def return_deposit_name_bank_name(s)->dict:
    
    """
        Получаем на вход строку, проверяем ее на содержание паттерна
        Отдаем список, в котором: 
        - на первом месте будет тип инструмента (вклад / накопительный счет),
        - на втором - название депозита
        - на третьем - название банка
    """
    
    match RegexEqual(s):
        # ВКЛАДЫ

        case r'^Вклад (?![Нн]акопительный)(.*?) от [Бб]анка (.+), условия':
            '''                
                TRUE: Вклад Привет от банка Т-Банк, условия, процентные ставки по депозиту
                TRUE: Вклад Привет с рукопожатием от банка Т-Банк, условия, процентные ставки по депозиту
                FALSE: Вклад Накопительный счёт от банка Т-Банк, условия, процентные ставки по депозиту
            '''
            
            
            search_pattern = re.search(r'^Вклад (?![Нн]акопительный)(.*?) от [Бб]анка (.+), условия', s)
            deposit_name = search_pattern.group(1)
            bank_name = search_pattern.group(2)
            return {
                'tool_type': 'Вклад',
                'deposit_name': deposit_name,
                'bank_name': bank_name
            }
            
            
        case r'^Вклад(?![Нн]акопительный) от [Бб]анка (.+), условия':
            '''                
                TRUE: Вклад от банка Почта Банк, условия, процентные ставки по счету
            '''
            search_pattern = re.search(r'^Вклад(?![Нн]акопительный) от [Бб]анка (.+), условия', s)
            # deposit_name = search_pattern.group(1)
            bank_name = search_pattern.group(1)
            return {
                'tool_type': 'Вклад',
                'deposit_name': 'Вклад',
                'bank_name': bank_name
            }
            
        case r'^(.+?\s[Вв]клад.*) от [Бб]анка (.+), условия':
            search_pattern = re.search(r'^(.+?\s[Вв]клад.*) от [Бб]анка (.+), условия', s)
            deposit_name = search_pattern.group(1)
            bank_name = search_pattern.group(2)
            return {
                'tool_type': 'Вклад',
                'deposit_name': deposit_name,
                'bank_name': bank_name
            }
            
            
        case r'^Вклад\/[Сс]ч[её]т (?![Нн]акопительный)(.*?) от [Бб]анка (.+), условия':
            
            search_pattern = re.search(r'^Вклад\/[Сс]ч[её]т (?![Нн]акопительный)(.*?) от [Бб]анка (.+), условия', s)
            deposit_name = search_pattern.group(1)
            bank_name = search_pattern.group(2)
            return {
                'tool_type': 'Вклад',
                'deposit_name': deposit_name,
                'bank_name': bank_name
            }
    
        
                        
        case r'(.+?[Вв]клад|.+?[Вв]клад .+) от [Бб]анка (.+), условия':
            search_pattern = re.search(r'(.+?[Вв]клад|.+?[Вв]клад .+) от [Бб]анка (.+), условия', s)
            deposit_name = search_pattern.group(1)
            bank_name = search_pattern.group(2)
            return {
                'tool_type': 'Вклад',
                'deposit_name': deposit_name,
                'bank_name': bank_name
            }
            
        case r'(.+?-[Вв]клад .+) от [Бб]анка (.+), условия':
            search_pattern = re.search(r'(.+?[Вв]клад) от [Бб]анка (.+), условия', s)
            deposit_name = search_pattern.group(1)
            bank_name = search_pattern.group(2)
            return {
                'tool_type': 'Вклад',
                'deposit_name': deposit_name,
                'bank_name': bank_name
            }
            
        
        # НАКОПИТЕЛЬНЫЙ СЧЕТ
        
        case r"^Накопительный [Сс]ч[её]т(.+?) от [Бб]анка (.+), условия":
            search_pattern = re.search(r'^Накопительный [Сс]ч[её]т(.+?) от [Бб]анка (.+), условия', s)
            deposit_name = search_pattern.group(1)
            bank_name = search_pattern.group(2)
            return {
                'tool_type': 'Накопительный счет',
                'deposit_name': deposit_name,
                'bank_name': bank_name
            }
            
        case r"^Вклад ([Нн]акопительный .*?[\s-][Сс]ч[её]т.*?|[Нн]акопительный [Сс]ч[её]т.*|[Нн]акопительный.*?) от [Бб]анка (.+), условия":
            search_pattern = re.search(r'^Вклад ([Нн]акопительный .*?[\s-][Сс]ч[её]т.*?|[Нн]акопительный [Сс]ч[её]т.*|[Нн]акопительный.*?) от [Бб]анка (.+), условия', s)
            deposit_name = search_pattern.group(1)
            bank_name = search_pattern.group(2)
            return {
                'tool_type': 'Накопительный счет',
                'deposit_name': deposit_name,
                'bank_name': bank_name
            }
            
        case r"^([Нн]акопительный.*?-[Сс]ч[её]т.*?|[Нн]акопительный [Cc]ч[её]т|[Нн]акопительный.*?|[Нн]акопительный [Сс]ч[её]т) от [Бб]анка (.+), условия":
            search_pattern = re.search(r"^([Нн]акопительный.*?-[Сс]ч[её]т.*?|[Нн]акопительный [Cc]ч[её]т|[Нн]акопительный.*?|[Нн]акопительный [Сс]ч[её]т) от [Бб]анка (.+), условия", s)
            deposit_name = search_pattern.group(1)
            bank_name = search_pattern.group(2)
            return {
                'tool_type': 'Накопительный счет',
                'deposit_name': deposit_name,
                'bank_name': bank_name
            }
                        
        case r"^[Сс]ч[её]т (Накопительный .+?) от [Бб]анка (.+), условия":
            search_pattern = re.search(r'^[Сс]ч[её]т (Накопительный .+?) от [Бб]анка (.+), условия', s)
            deposit_name = search_pattern.group(1)
            bank_name = search_pattern.group(2)
            return {
                'tool_type': 'Накопительный счет',
                'deposit_name': deposit_name,
                'bank_name': bank_name
            }
            
def return_min_max_deposit_term(s)->dict:
    
    """A naive string validator"""
    
    match RegexEqual(s):
        
        case r"[Оо]т (\d*\s?\d*) до (\d*)":
            search_pattern = re.search(r'[Оо]т (\d*\s?\d*) до (\d*)', s)
            min_value = float(search_pattern.group(1).replace(' ', '').strip())
            max_value = float(search_pattern.group(2).replace(' ', '').strip())
            return {'min_value': min_value, 'max_value': max_value}
        
        case r"[Оо]т (.*)":
            search_pattern = re.search(r'[Оо]т (.*)', s)
            min_value = float(search_pattern.group(1).replace(' ', '').strip())
            return {'min_value': min_value, 'max_value': None}            
        
        case r"[дД]о (.*)":
            search_pattern = re.search(r'[дД]о (.*)', s)
            max_value = float(search_pattern.group(1).replace(' ', '').strip())
            return {'min_value': None, 'max_value': max_value}
        
        case r"(.+)\s?-\s?(.+)":
            search_pattern = re.search(r'(.+)\s?-\s?(.+)', s)
            min_value = float(search_pattern.group(1).replace(' ', '').strip())
            max_value = float(search_pattern.group(2).replace(' ', '').strip())
            return {'min_value': min_value, 'max_value': max_value}
        
        case r"не огран":
            return {'min_value': 0, 'max_value': 999999999}
        
        # only digits
        case r"\d+\s?\d+":
            search_pattern = re.search(r'\d+\s?\d+', s)
            min_value = float(search_pattern.group(0).replace(' ', '').strip())
            return {'min_value': min_value, 'max_value': 999999999}
        
        
        
def match_days_range(s)->dict:
    match RegexEqual(s):        
        case r"(\d*)-(\d*) (дней|день|дня)":
            search_pattern = re.search(r"(\d*)-(\d*) (дней|день|дня)", s)
            min_days_value = int(search_pattern.group(1))
            max_days_value = int(search_pattern.group(2))
            return {'min_days_value': min_days_value, 'max_days_value': max_days_value}
        
        case r"[Оо]т (\d*) (дней|день|дня)$":
            search_pattern = re.search(r"[Оо]т (\d*) (дней|день|дня)$", s)
            min_days_value = int(search_pattern.group(1))
            return {'min_days_value': min_days_value, 'max_days_value': None}
        
        case r'^(\d*) (дней|день|дня)$':
            search_pattern = re.search(r'^(\d*) (дней|день|дня)$', s)
            min_days_value = int(search_pattern.group(1))
            return {'min_days_value': min_days_value, 'max_days_value': None}
        
        case r'^[Оо]т (\d+)\s*?(дней|день|дня)$':
            search_pattern = re.search(r'^[Оо]т (\d+)\s*?(дней|день|дня)$', s)
            min_days_value = int(search_pattern.group(1))
            return {'min_days_value': min_days_value, 'max_days_value': None}
        
        
def rate_search(s)->dict:
    match RegexEqual(s):        
        case r"<td>(.+)%\s?<\/td>":
            search_pattern = re.search(r"<td>(.+)%\s?<\/td>", s)
            try:
                return float(search_pattern.group(1).strip())
            except:
                return None