import os
import feedparser
import re
import requests
from google import genai
from datetime import datetime

# --- KONFIGURACE ---
RSS_FEEDS = [
    "https://www.e15.cz/rss",
    "https://hn.cz/?m=rss",
    "https://cc.cz/feed/",
    "https://servis.idnes.cz/rss.aspx?c=ekonomikah",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml"
    "https://www.wired.com/feed/category/business/latest/rss"

]

SEEN_URLS_FILE = "seen_urls.txt"
# Model gemini-2.0-flash je doporučená volba pro rychlost a kvalitu
MODEL_NAME = "gemini-2.5-flash" 

def clean_html(text):
    """Odstraní HTML tagy z popisu článku."""
    if not text:
        return ""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()

def load_seen_urls():
    """Načte již zpracované URL ze souboru."""
    if not os.path.exists(SEEN_URLS_FILE):
        return set()
    with open(SEEN_URLS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_seen_urls(urls):
    """Uloží nové URL do souboru."""
    with open(SEEN_URLS_FILE, "a", encoding="utf-8") as f:
        for url in urls:
            f.write(f"{url}\n")

def get_new_articles(feeds, seen_urls):
    """Stáhne články z RSS a vyfiltruje ty, které jsme už viděli."""
    new_articles = []
    for feed_url in feeds:
        print(f"Stahuji RSS: {feed_url}")
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            link = entry.link
            if link not in seen_urls:
                new_articles.append({
                    "title": entry.title,
                    "link": link,
                    "description": clean_html(getattr(entry, "summary", ""))
                })
    return new_articles

def analyze_with_gemini(articles):
    """Pošle články do Gemini k analýze a shrnutí."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Chyba: GEMINI_API_KEY není nastaven v prostředí.")
        return None

    client = genai.Client(api_key=api_key)
    
    # Příprava promptu
    content_to_analyze = "\n\n".join([
        f"Titulek: {a['title']}\nURL: {a['link']}\nPopis: {a['description']}" 
        for a in articles
    ])
    
    prompt = f"""
    Jsi můj osobní informační kurátor. Tvým úkolem je z následujících zpráv vybrat 6 nejzajímavějších kousků, které odpovídají mým zájmům.

    MÉ ZÁJMY (podle nich vybírej):
    - Zajímavosti z byznysu a startupového světa.
    - Mergery, akvizice, aliance, strategická rozhodnutí.
    - Události na burzách
    - Pokroky v AI a nové technologie.
    - Ekonomické trendy, které ovlivňují běžný život nebo investice.
    - Energetika (např. jaderné reaktory, obnovitelné zdroje).
    - Politika
    - Cokoliv, co je unikátní, inovativní nebo se vymyká běžným zprávám.

    INSTRUKCE:
    - Vyber přesně 6 zpráv (pokud jich je v seznamu dostatek).
    - Vyhni se bulvárním článkům.
    - Pokud je zdroj v angličtině, shrnutí napiš česky.
    - Piš věcně, ale zajímavě, žádný suchý korporátní styl.

    FORMÁT PRO KAŽDOU ZPRÁVU:
    💡 <b>TITULEK</b>
    Shrnutí: Co se děje a proč by mě to mělo zajímat (max 3-4 věty).
    <a href='URL'>Číst více</a>

    STRIKTNÍ PRAVIDLA PRO FORMÁT:
    1. Nepoužívej ŽÁDNÉ HTML tagy kromě <b> a <a>.
    2. Pro nové řádky používej pouze běžný Enter.
    3. Pod titulkem nech volný řádek. Mezi zprávami nechej dva volné řádky.
    4. Nepoužívej hvězdičky (**), podtržítka (_) ani kurzívu.

    Zprávy k analýze:
    {content_to_analyze}
    """

    print("Odesílám analýzu do Gemini...")
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"Chyba při volání Gemini API: {e}")
        return None

def send_telegram_message(text):
    """Odešle zprávu na Telegram (pokud jsou nastaveny klíče)."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("Telegram klíče nejsou nastaveny, přeskakuji odesílání.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        resp = requests.post(url, json=payload)
        resp.raise_for_status()
        print("Zpráva úspěšně odeslána na Telegram.")
    except Exception as e:
        print(f"Chyba při odesílání na Telegram: {e}")

def main():
    print(f"--- Spouštím eko_bot ({datetime.now().strftime('%d.%m.%Y %H:%M:%S')}) ---")
    
    seen_urls = load_seen_urls()
    new_articles = get_new_articles(RSS_FEEDS, seen_urls)
    
    if not new_articles:
        print("Dnes žádné nové zprávy.")
        return

    print(f"Nalezeno {len(new_articles)} nových článků.")
    
    # Analýza v Gemini
    analysis_result = analyze_with_gemini(new_articles)
    
    if analysis_result:
        # Výpis do konzole
        print("\n--- VÝSLEDEK ANALÝZY ---")
        print(analysis_result)
        print("------------------------\n")
        
        # Odeslání na Telegram
        send_telegram_message(analysis_result)
        
        # Uložení historie (pouze pokud proběhla analýza)
        new_links = [a['link'] for a in new_articles]
        save_seen_urls(new_links)
    else:
        print("Analýza se nezdařila.")

if __name__ == "__main__":
    main()
