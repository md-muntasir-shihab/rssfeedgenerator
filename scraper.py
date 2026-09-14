import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
import feedparser
from feedgen.feed import FeedGenerator
import trafilatura

# ==============================================================================
#                  আপনার কনফিগার করা সকল সোর্সের তালিকা
# ==============================================================================

WEBSITE_URLS = [
    "https://thedailycampus.com/latest",
    "https://www.prothomalo.com/chakri",
    "https://www.ru.ac.bd/"
]

TELEGRAM_CHANNELS = [
    "admissionnewsnetwork"
]

FACEBOOK_PAGES = [
    "admissionnewsnetworkofficial",
    "kuinsidersofficial",
    "Officials.DUInsiders",
    "thedailycampusoriginal",
    "JUinsiders",
    "ru.insiders"
]

FEED_TITLE = "Campus & Career Master Feed"
FEED_DESC = "All-in-one verified news, notices, and updates updated every 30 minutes."
FEED_FILE = "feed.xml"
FEED_URL = "https://md-muntasir-shihab.github.io/rssfeedgenerator/feed.xml"

# ফেসবুক স্ক্র্যাপ করার বিকল্প মিরর সার্ভার (একটি ফেইল করলে অন্যটি কাজ করবে)
RSSHUB_MIRRORS = [
    "https://rsshub.app",
    "https://rsshub.rssforever.com",
    "https://rss.itggg.cn"
]
# ==============================================================================

# ১. নেটওয়ার্ক রিট্রাই ইঞ্জিন (কানেকশন ড্রপ ঠেকানোর জন্য)
def get_robust_session():
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "bn-BD,bn;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    return session

SESSION = get_robust_session()

def clean_html_content(raw_text):
    """লেখা থেকে অপ্রয়োজনীয় কোড, বিজ্ঞাপন ও ফুটনোট পরিষ্কার করা"""
    if not raw_text:
        return ""
    text = re.sub(r'!\[.*?\]\(.*?\)', '', raw_text)
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    text = text.replace('**', '').replace('*', '')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def parse_full_article(article_url):
    """আর্টিকেলের ভেতরে ঢুকে বড় ছবি, তারিখ ও পুরো টেক্সট নিয়ে আসা"""
    try:
        res = SESSION.get(article_url, timeout=12)
        if res.status_code != 200:
            return None

        page_soup = BeautifulSoup(res.text, "html.parser")
        downloaded = res.text

        metadata = trafilatura.extract_metadata(downloaded)
        full_text = trafilatura.extract(
            downloaded,
            include_images=True,
            include_formatting=False,
            output_format="txt"
        )

        title = metadata.title if (metadata and metadata.title) else None
        if not title and page_soup.title:
            title = page_soup.title.get_text().split("-")[0].split("|")[0].strip()

        if not title or len(title) < 5:
            return None

        # হাই-রেজুলেশন ইমেজ ডিটেকশন
        image_url = metadata.image if (metadata and metadata.image) else None
        if not image_url:
            for prop in ["og:image", "twitter:image"]:
                tag = page_soup.find("meta", property=prop) or page_soup.find("meta", attrs={"name": prop})
                if tag and tag.get("content"):
                    image_url = urljoin(article_url, tag["content"])
                    break

        pub_date = datetime.now(timezone.utc)
        if metadata and metadata.date:
            try:
                pub_date = date_parser.parse(metadata.date).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        cleaned = clean_html_content(full_text)
        paragraphs = [f"<p>{p.strip()}</p>" for p in cleaned.split("\n\n") if len(p.strip()) > 20]
        
        # রিডারের জন্য পরিপাটি ম্যাগাজিন লেআউট
        content_components = []
        if image_url:
            content_components.append(
                f'<p><img src="{image_url}" alt="{title}" style="max-width:100%; height:auto; border-radius:8px;"/></p>'
            )
        content_components.extend(paragraphs[:8])
        final_html = "".join(content_components) if content_components else f"<p>{title}</p>"

        summary_text = cleaned[:250] + "..." if len(cleaned) > 250 else title

        return {
            "title": title.strip(),
            "url": article_url,
            "image": image_url,
            "date": pub_date,
            "summary": summary_text,
            "content_html": final_html
        }
    except Exception:
        return None

def scrape_website(target_url):
    items = []
    try:
        res = SESSION.get(target_url, timeout=15)
        if res.status_code != 200:
            return items

        soup = BeautifulSoup(res.text, "html.parser")
        discovered_links = []
        seen = set()

        for a in soup.find_all("a", href=True):
            full_url = urljoin(target_url, a["href"].strip())
            if full_url == target_url or full_url in seen:
                continue
            if any(bad in full_url.lower() for bad in ["#", "/tag/", "/category/", "/author/", "login", "facebook.com", "twitter.com"]):
                continue

            if len(full_url.replace(target_url, "")) > 4:
                seen.add(full_url)
                discovered_links.append(full_url)

        # প্রতি সাইটের শীর্ষ ১২টি নতুন খবর চেক করবে
        for link in discovered_links[:12]:
            data = parse_full_article(link)
            if data:
                items.append(data)
    except Exception as e:
        print(f"Error scraping {target_url}: {e}")
    return items

def scrape_telegram(channel):
    items = []
    try:
        url = f"https://t.me/s/{channel}"
        res = SESSION.get(url, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        for msg in soup.find_all("div", class_="tgme_widget_message_wrap")[-15:]:
            text_el = msg.find("div", class_="tgme_widget_message_text")
            date_el = msg.find("time")
            link_el = msg.find("a", class_="tgme_widget_message_date")
            if not text_el or not link_el:
                continue

            raw_text = text_el.get_text(separator="\n", strip=True)
            title = raw_text[:85] + "..." if len(raw_text) > 85 else raw_text
            post_link = link_el.get("href")

            pub_date = datetime.now(timezone.utc)
            if date_el and date_el.get("datetime"):
                try:
                    pub_date = date_parser.parse(date_el["datetime"]).replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            image_url = None
            photo = msg.find("a", class_="tgme_widget_message_photo_wrap")
            if photo and photo.get("style"):
                match = re.search(r"url\('(.*?)'\)", photo["style"])
                if match:
                    image_url = match.group(1)

            html_body = ""
            if image_url:
                html_body += f'<p><img src="{image_url}" style="max-width:100%; border-radius:8px;"/></p>'
            html_body += f"<p>{raw_text.replace(chr(10), '<br/>')}</p>"

            items.append({
                "title": f"[Telegram] {title}",
                "url": post_link,
                "image": image_url,
                "date": pub_date,
                "summary": title,
                "content_html": html_body
            })
    except Exception as e:
        print(f"Telegram error {channel}: {e}")
    return items

def fetch_facebook(page_id):
    """একাধিক মিরর ব্যবহার করে নিশ্চিতভাবে ফেসবুক পোস্ট নিয়ে আসা"""
    items = []
    for mirror in RSSHUB_MIRRORS:
        feed_url = f"{mirror}/facebook/page/{page_id}"
        try:
            res = SESSION.get(feed_url, timeout=8)
            if res.status_code == 200 and "<rss" in res.text:
                parsed = feedparser.parse(res.text)
                for entry in parsed.entries[:6]:
                    title = entry.get("title", f"Update from {page_id}")
                    link = entry.get("link", feed_url)
                    content = entry.get("summary", "")

                    pub_date = datetime.now(timezone.utc)
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                    img_match = re.search(r'<img[^>]+src="([^">]+)"', content)
                    image_url = img_match.group(1) if img_match else None

                    items.append({
                        "title": f"[FB] {title[:85]}",
                        "url": link,
                        "image": image_url,
                        "date": pub_date,
                        "summary": title[:200],
                        "content_html": content
                    })
                if items:
                    break
        except Exception:
            continue
    return items

def build_feed():
    new_items = []

    for url in WEBSITE_URLS:
        new_items.extend(scrape_website(url))

    for ch in TELEGRAM_CHANNELS:
        new_items.extend(scrape_telegram(ch))

    for fb_page in FACEBOOK_PAGES:
        new_items.extend(fetch_facebook(fb_page))

    # পুরোনো ফিড ধরে রাখা (হিস্ট্রি যাতে ডিলিট না হয়)
    existing_items = []
    if os.path.exists(FEED_FILE):
        try:
            old_feed = feedparser.parse(FEED_FILE)
            for entry in old_feed.entries:
                pub_d = datetime.now(timezone.utc)
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_d = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                img_url = None
                if hasattr(entry, "enclosures") and entry.enclosures:
                    img_url = entry.enclosures[0].get("href")

                existing_items.append({
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "date": pub_d,
                    "image": img_url,
                    "summary": entry.get("summary", ""),
                    "content_html": entry.get("content", [{}])[0].get("value", entry.get("description", ""))
                })
        except Exception:
            pass

    # মার্জ ও ডুপ্লিকেট বাদ দেওয়া
    all_combined = []
    seen_urls = set()

    for item in (new_items + existing_items):
        if item.get("url") and item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            all_combined.append(item)

    all_combined.sort(key=lambda x: x["date"], reverse=True)

    # Feedly স্ট্যান্ডার্ড RSS 2.0 জেনারেটর
    fg = FeedGenerator()
    fg.id(FEED_URL)
    fg.title(FEED_TITLE)
    fg.link(href=FEED_URL, rel="self")
    fg.description(FEED_DESC)
    fg.language("bn")

    # শীর্ষ ১২০টি খবর ফিডে জমা রাখা
    for item in all_combined[:120]:
        entry = fg.add_entry()
        entry.id(item["url"])
        entry.title(item["title"])
        entry.link(href=item["url"])
        entry.pubDate(item["date"])
        entry.description(item["summary"])

        if item.get("image"):
            entry.enclosure(url=item["image"], type="image/jpeg", length="0")

        # Feedly-তে ফুল টেক্সট ও ছবি পরিপাটি দেখানোর জন্য CDATA কনটেন্ট
        entry.content(item["content_html"], type="CDATA")

    fg.rss_file(FEED_FILE, pretty=True)
    print("Master Feed with full Feedly-compatibility generated successfully!")

if __name__ == "__main__":
    build_feed()
