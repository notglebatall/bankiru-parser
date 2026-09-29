#!/python_projects/venvs/dbra_venv/bin/activate

import requests
from bs4 import BeautifulSoup as bs
from bs4 import Tag

import copy

import time
from datetime import datetime

import re
import os

from tqdm import tqdm

import pandas as pd
import matplotlib as plt
from copy import deepcopy

import pickle

import json
import random

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

import match_case_eq

os.chdir("C:/VD/Парсер/bankiros_parser")

with open('bank_dict.json', 'r') as fp:
    bank_dict = json.load(fp)    


with open('userAgents.json') as f:
    ua = json.load(f)

        
# set links for start parse
bankiros_link = "https://bankiros.ru/deposits?page=1"
main_link = 'https://bankiros.ru'


print(f'start connect to {main_link}')
ua_random = random.choice(ua)
headers = {'User-Agent': ua_random}
html = requests.get(bankiros_link, headers=headers, timeout=1000)

# set random user agent
while html.status_code != 200:
    time.sleep(15)
    ua_random = random.choice(ua)
    headers = {'User-Agent': ua_random}
    html = requests.get(bankiros_link, headers=headers, timeout=1000)

print(f'status code is 200')
html.encoding='utf-8'
page = html.text
soup = bs(page, 'lxml')

rows_on_page = soup.find("a", {"id":"product-list-pagination"})
rows_on_page_int = int(rows_on_page['data-total-count'])

total_rows = soup.find("span", {"data-js":"filter-count"})
total_rows_int = int(total_rows.text)

def int_ceil(a, b):
    return (a - 1) // b + 1

pages_for_loop = int_ceil(total_rows_int, rows_on_page_int)


# set options for selenium web driver
options = Options()
# options.headless = True
options.add_argument("--headless")
options.add_argument("--no-sandbox")

# init web driver
driver = webdriver.Chrome(options=options)  # or webdriver.Firefox()
driver.get(bankiros_link)

# press "Показать еще"
print(f'init Selenium and press button')
for i in tqdm(range(1, pages_for_loop+1)):
    try:
        driver.find_element("xpath", '//a[contains(., "Показать еще")]').click()
        time.sleep(5)
    except:
        pass

# get full html
elem = driver.find_element("xpath", "//*")
source_code = elem.get_attribute("outerHTML")




deposits_links_list = []

soup = bs(source_code, 'lxml')
driver.quit()

for div in soup.find_all('div', class_ = 'xxx-table-list__row-inner'):
    for i, div_list_cell in enumerate(div.find_all('div', class_ = 'xxx-table-list__cell')):
    
        if i == 5:
            # print(div_list_cell.prettify())
            regn_raw = div_list_cell.find('span', class_ = 'xxx-table-list__mini-text xxx-desk-visible xxx-mb-10')
            link_raw = div_list_cell.find('span', class_ = 'xxx-g-link xxx-mob-visible get-product-modal')
            
            link = f"{main_link}{link_raw['data-url']}"
            
            re_regn = re.compile(r'\d+')
            

            try:
                regn = re_regn.search(regn_raw.text).group(0)
            except:
                regn = 'нет регномера'
                
            if (link, regn) not in deposits_links_list:
                deposits_links_list.append((link, regn))    
    
wrong_parse = []
already_read = []

total_list = []

print(f'start parse deposits links')

for i in tqdm(range(len(deposits_links_list))):    
    time.sleep(random.randint(0,3))
    
    deposit_link, bank_regn  = deposits_links_list.pop(0)
    
    deposit_list = []
    
    html = requests.get(deposit_link, headers=headers, timeout=1000)
    
    # если не 200 - ждем 15 секунд и пробуем еще раз
    while html.status_code != 200:
        time.sleep(15)
        ua_random = random.choice(ua)
        headers = {'User-Agent': ua_random}        
        html = requests.get(deposit_link, headers=headers, timeout=1000)
            
    html.encoding='utf-8'
    page = html.text
    
    soup = bs(page, 'lxml')
    
    title_another = soup.find('title').text
    data_relation_id = soup.find('button', class_='js-our-counter xxx-g-btn-voting__item xxx-g-btn-voting__item--like')['data-relation_id']
    title_after_preprocess = match_case_eq.return_deposit_name_bank_name(title_another)
        
    if title_after_preprocess == None:
        print('error')
        print(title_another)
        print(deposit_link)
        break
    
    
    deposit_conditions = {}
    
    for div in soup.find_all('div', class_="xxx-products-page__tab-column"):
        for li in div.find_all('li', class_="xxx-g-list__item"):
            li_list = li.text.split(': ')
            deposit_conditions[li_list[0]] = li_list[1]
    
    # индекс рублей
    rub_rate = ''
    
    for ind, li in enumerate(soup.find_all('ul', class_ = 'xxx-tab__list xxx-products-page__info-tabs-menu')[1]):
        if 'RUB' in li.text:
            # print(ind, li['data-tab'])
            rub_rate = li['data-tab'].replace('.', '')
    
    table_div = soup.find('div', class_ = f'xxx-switched-rate-table {rub_rate} active')
    
    # extact table from prev div
    table_w_rates = table_div.find('table', class_ = 'xxx-table-default--mob-rate-contribution').extract()
    
    
    # separate table head and table body from table
    table_head = table_w_rates.find('thead')
    table_body = table_w_rates.find('tbody')
    
    
    # modify head
    table_head_mod = []
    
    for row in table_head:
        for cell in row("td"):
            table_head_mod.append(cell.text.strip())
    
    
    table_head_list_of_dicts = []
    
    for i, elem in enumerate(table_head_mod):
        elem = elem.strip()
        if i == 0:
            pass
            # table_head_list_of_dicts.append(elem)
        else:
            try:
                elem_dict = match_case_eq.match_days_range(elem)
                assert isinstance(elem_dict, dict)
                table_head_list_of_dicts.append(elem_dict)
            except Exception as e:
                print(f'{e}, не могу распарсить: {elem}', deposit_link, sep='\n')
                raise Exception("не могу распарсить")
                    
    for i, elem in enumerate(table_head_list_of_dicts):
        if isinstance(elem, dict):
            if i == 1 and elem['min_days_value'] == None:
                elem['min_days_value'] = 1
            elif elem['min_days_value'] == None:
                elem['min_days_value'] = table_head_list_of_dicts[i-1]['max_days_value']+1
            elif i == len(table_head_list_of_dicts)-1 and elem['max_days_value'] is None:
                elem['max_days_value'] = 9999
            elif elem['max_days_value'] is None:
                elem['max_days_value'] = table_head_list_of_dicts[i+1]['min_days_value']-1    
    
    # get table body from table
    table_body_prep = []
    
    for row in table_body:
        temp_list = []
        for i, cell in enumerate(row('td')):
            if i == 0:
                temp_list.append(cell.text)
            else:
                cell_str = re.sub(r'<div.+<\/div>', '', str(cell))
                try:
                    # rate = re.search(r'<td>(.+)%\s?<\/td>', cell_str).group(1).strip()
                    rate = match_case_eq.rate_search(cell_str)
                except Exception as e:
                    print(f'{e}, не могу распарсить: {cell}', cell_str, table_body, deposit_link, sep='\n')
                    raise Exception("не могу распарсить")
                    
                temp_list.append(rate)
        table_body_prep.append(temp_list)
    
    min_max_deposits_values = []
    rate_value = []
    
    for elem in table_body_prep:
        temp_list = []
        for i, x in enumerate(elem):
            if i == 0:
                try:
                    mod_x = match_case_eq.return_min_max_deposit_term(x)
                    assert isinstance(mod_x, dict)
                    min_max_deposits_values.append(mod_x)
                    # temp_list.append(mod_x)
                except Exception as e:
                    print(f'{e}, не могу распарсить: {x} / {deposit_link}')
                    break
            else:
                rate_value.append({'rate_value': x})
    
    for i, elem in enumerate(min_max_deposits_values):
        if i == 0 and elem['min_value'] is None:
            elem['min_value'] = float(0)
        elif elem['min_value'] is None:
            elem['min_value'] = min_max_deposits_values[i-1]['max_value']+1
        elif i == len(min_max_deposits_values)-1 and elem['max_value'] is None:
            elem['max_value'] = 999999999
        elif elem['max_value'] is None:
            elem['max_value'] = min_max_deposits_values[i+1]['min_value']-1
    
    idx = 0
    
    for i in min_max_deposits_values:
        for ii in table_head_list_of_dicts:
            temp_dict = {}
            temp_dict = temp_dict|i
            temp_dict = temp_dict|ii
            
            cur_rate = rate_value[idx]
            temp_dict = temp_dict|cur_rate
            
            try:
                if title_after_preprocess['bank_name'] in bank_dict.keys():
                    title_after_preprocess['bank_name'] = bank_dict[title_after_preprocess['bank_name']]
                
                temp_dict['bank_name'] = title_after_preprocess['bank_name']
                temp_dict['deposit_name'] = title_after_preprocess['deposit_name']
                temp_dict['tool_type'] = title_after_preprocess['tool_type']
                temp_dict['regn'] = bank_regn
                temp_dict['deposit_link'] = deposit_link
                temp_dict = temp_dict|deposit_conditions
            
            except Exception as e:
                print(f'{e}, неправильно распарсили: {title_after_preprocess}, {title_another}, {deposit_link}')
                
                if (deposit_link, bank_regn) not in wrong_parse:
                    wrong_parse.append((deposit_link, bank_regn))
                
            total_list.append(temp_dict)
            idx+=1
    
    already_read.append(deposit_link)    


# create success df
df = pd.DataFrame(total_list)
df['date_parse'] = datetime.today().strftime("%Y-%m-%d")

try:    
    df.to_excel(f'{datetime.today().strftime("%Y-%m-%d")}.xlsx', index=False)
except:
    with open('parrot.pkl', 'wb') as f:
        pickle.dump(total_list, f)            

# create wrong parse df if 'wrong_parse' list is not empty
if len(wrong_parse)>0:
    df = pd.DataFrame(wrong_parse)
    try:
        df.to_excel(f'WRONG_PARSE_{datetime.today().strftime("%Y-%m-%d")}.xlsx', index=False)
    except:
        with open('WRONG_PARSE.pkl', 'wb') as f:
            pickle.dump(total_list, f)