import signal
import sys
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
import logging
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import spacy

nlp = spacy.load("ru_core_news_md")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

KEYWORDS = [
    "погиб", "убит", "скончался", "умер", "смерть", "загинув",
    "погибла", "убита", "скончалась", "смерти", "убийство", "казнь",
    "пал", "убитый", "ушел из жизни", "отдал жизнь", "внезапная смерть",
    "трагедия", "несчастный случай", "кончина", "гибель", "погибший",
    "преступление", "расстрел", "похоронен", "труп", "найден мертвым",
    "умерший", "мертв", "расстрелян", "подорвался", "раненый",
    "взорвался", "умершая", "смертельная рана", "самоубийство",
    "жертва", "сбит", "обстрел", "насилие", "ликвидирован",
    "простились", "погибшим", "похороны", "захоронение", "погибшие",
    "память", "траур", "проводили в последний путь", "прощание",
    "прощались", "посмертно", "вдова", "вдовец", "погибшего",
    "павшие", "утрата", "последние слова", "катастрофа", "авария",
    "перестрелка", "теракт", "потеря", "пропал без вести", "жертвы",
    "массовое убийство", "убийца", "стрелок", "атака", "экзекуция",
    "судьба", "фатальный", "мученик", "погибель", "кладбище"
]

STOPWORDS = {
    "Ему", "Его", "Ее", "Им", "Их", "Него", "Нему", "Ней", "Ним", "Нею",
    "Она", "Он", "Они"
}

NAME_REGEX = r'\b[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\b'
EXCLUSION_WORDS = {"Жизнь", "День", "Событие", "Смерть"}

deceased_names = set()

def save_data_on_termination(signum, frame):
    logging.info("Termination signal received. Exiting...")
    if deceased_names:
        print("Final list of deceased names:")
        for name in deceased_names:
            print(name)
    sys.exit(0)

signal.signal(signal.SIGINT, save_data_on_termination)
signal.signal(signal.SIGTERM, save_data_on_termination)

def setup_driver(proxy_address=None):
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
    )
    if proxy_address:
        options.add_argument(f'--proxy-server={proxy_address}')
    driver = webdriver.Chrome(options=options)
    return driver

def is_valid_name(name):
    parts = name.split()

    if len(parts) != 2:
        logging.info(f"Invalid name (doesn't have two parts): {name}")
        return False

    first_name, last_name = parts

    if first_name in EXCLUSION_WORDS or last_name in EXCLUSION_WORDS:
        logging.info(f"Invalid name (exclusion word found): {name}")
        return False

    if not first_name[0].isupper() or not last_name[0].isupper() or first_name in STOPWORDS or last_name in STOPWORDS:
        logging.info(f"Invalid name (capitalization/stopword): {name}")
        return False

    if not (2 <= len(first_name) <= 25 and 2 <= len(last_name) <= 25):
        logging.info(f"Invalid name (length check failed): {name}")
        return False

    doc = nlp(name)
    if any(ent.label_ == 'PER' for ent in doc.ents):
        return True

    logging.info(f"Name not recognized by NER: {name}")
    return False

def contains_death_related_keywords(headline):
    return any(keyword in headline.lower() for keyword in KEYWORDS)

def extract_names_with_regex(text):
    matches = re.findall(NAME_REGEX, text)
    valid_names = [name for name in matches if is_valid_name(name)]
    return valid_names

def scrape_headlines_and_paragraphs(driver):
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'lxml')
    
    containers = soup.select('div.all-news__list_text-container')
    
    headline_texts = []
    for container in containers:
        headline = container.find('h2', class_='oneNews__link').get_text().strip()
        paragraph = container.find('p', class_='oneNews__link').get_text().strip()
        headline_texts.append((headline, paragraph))
    
    logging.info(f"Scraped {len(headline_texts)} headlines and paragraphs.")
    return headline_texts

def click_next_button(driver):
    try:
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//a[contains(@class, "all-news__button_forward") and contains(., "Далее ❯")]'))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
        time.sleep(1)
        try:
            next_button.click()
            logging.info("Navigated to the next page.")
        except:
            driver.execute_script("arguments[0].click();", next_button)
            logging.info("Navigated to the next page using JavaScript click.")
        return True
    except Exception as e:
        logging.warning(f"Error or end of pages: {e}")
        return False

def crawl_pages(start_url):
    driver = setup_driver()
    try:
        driver.get(start_url)
        while True:
            headlines_and_paragraphs = scrape_headlines_and_paragraphs(driver)
            for headline, paragraph in headlines_and_paragraphs:
                if contains_death_related_keywords(headline):
                    combined_text = f"{headline} {paragraph}"
                    names = extract_names_with_regex(combined_text)
                    if names:
                        deceased_names.update(names)
                        logging.info(f"Deceased names found: {', '.join(names)}")

            if not click_next_button(driver):
                break
            time.sleep(2)
    finally:
        driver.quit()
        if deceased_names:
            print("Final list of deceased names:")
            for name in deceased_names:
                print(name)

def main():
    url = "https://pestrecy-rt.ru/news/tag/list/specoperaciia/"
    crawl_pages(url)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(1)
