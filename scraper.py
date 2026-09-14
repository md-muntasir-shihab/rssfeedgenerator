import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
import feedparser
from feedgen.feed import FeedGenerator
import trafilatura

# ==============================================================================
#                  আপনার দেওয়া সকল সোর্সের তালিকা
# ==============================================================================

# ১. ওয়েবসাইট ও পোর্টাল
WEBSITE_URLS = [
    "https://thedailycampus.com/latest",
    "https://www.prothomalo.com/chakri",
    "https://www.ru.ac.bd/"
]

# ২. টেলিগ্রাম চ্যানেল
TELEGRAM_CHANNELS = [
    "admissionnewsnetwork"
]

# ৩. ফেসবুক পেজ (RSSHub ব্রিজের মাধ্যমে অটো-ফেচ হবে)
FACEBOOK_PAGES = [
    "admissionnewsnetworkofficial",
    "kuinsidersofficial",
    "Officials.DUInsiders",
    "thedailycampusoriginal",
    "JUinsiders",
    "ru.insiders"
]

FEED_TITLE = "Campus & Career Unified News Feed"
FEED_DESC = "All-in-one updates from Daily Campus, Prothom Alo Chakri, RU, Telegram & Insiders pages."
FEED_FILE = "feed.xml"
# ==============================================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "bn-BD,bn;q=0.9,en-US;q=0.8,en;q=0.7",
}

def clean_text(raw_text):
    if not raw_text:
        return ""
    text = re.sub(r'!\[.*?\]\(.*?\)', '', raw_text)
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    text = text.replace('**', '').replace('*', '')
    return text.strip()

def parse_full_article(article_url):
    """ওয়েব আর্টিকেলের ভেতর ঢুকে পুরো খবর ও ছবি বের করা"""
    try:
        res = requests.get(article_url, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            return None

        page_soup = BeautifulSoup(res.text, "html.parser")
        downloaded = res.text

        metadata = trafilatura.extract_metadata(downloaded)
        full_text = trafilatura.extract(downloaded, output_format="txt")

        title = metadata.title if (metadata and metadata.title) else None
        if not title and page_soup.title:
            title = page_soup.title.get_text().split("-")[0].split("|")[0].strip()

        if not title or len(title) < 5:
            return None

        # কাভার ছবি খোঁজা
        image_url = metadata.image if (metadata and metadata.image) else None
        if not image_url:
            og_img = page_soup.find("meta", property="og:image") or page_soup.find("meta", attrs={"name": "twitter:image"})
            if og_img and og_img.get("content"):
                image_url = urljoin(article_url, og_img["content"])

        pub_date = datetime.now(timezone.utc)
        if metadata and metadata.date:
            try:
                pub_date = date_parser.parse(metadata.date).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        cleaned = clean_text(full_text)
        paragraphs = [f"<p>{p.strip()}</p>" for p in cleaned.split("\n\n") if len(p.strip()) > 20]
        content_html = "".join(paragraphs[:6]) if paragraphs else f"<p>{title}</p>"

        return {
            "title": title.strip(),
            "url": article_url,
            "image": image_url,
            "date": pub_date,
            "content": content_html
        }
    except Exception:
        return None

def scrape_website(target_url):
    items = []
    try:
        res = requests.get(target_url, headers=HEADERS, timeout=15)
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

            # নিউজ আর্টিকেলের মতো লিংক ফিল্টার
            if len(full_url.replace(target_url, "")) > 4:
                seen.add(full_url)
                discovered_links.append(full_url)

        # প্রতিটি সাইটের সর্বশেষ ৩টি নিউজ স্ক্র্যাপ করবে
        for link in discovered_links[:3]:
            data = parse_full_article(link)
            if data:
                items.append(data)
    except Exception as e:
        print(f"Error scraping website {target_url}: {e}")
    return items

def scrape_telegram(channel):
    items = []
    try:
        url = f"https://t.me/s/{channel}"
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        for msg in soup.find_all("div", class_="tgme_widget_message_wrap")[-4:]:
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

            html_body = f"<p>{raw_text.replace(chr(10), '<br/>')}</p>"
            items.append({
                "title": f"[Telegram] {title}",
                "url": post_link,
                "image": image_url,
                "date": pub_date,
                "content": html_body
            })
    except Exception as e:
        print(f"Telegram error {channel}: {e}")
    return items

def fetch_facebook(page_id):
    """ফেসবুক পেজ থেকে RSSHub ব্রিজ ব্যবহার করে ডেটা নেওয়া"""
    items = []
    feed_url = f"https://rsshub.app/facebook/page/{page_id}"
    try:
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries[:2]:
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
                "content": content
            })
    except Exception as e:
        print(f"Facebook page skip {page_id}: {e}")
    return items

def build_feed():
    all_news = []

    # ১. ওয়েবসাইটগুলো স্ক্র্যাপ করা
    for url in WEBSITE_URLS:
        all_news.extend(scrape_website(url))

    # ২. টেলিগ্রাম থেকে আনা
    for ch in TELEGRAM_CHANNELS:
        all_news.extend(scrape_telegram(ch))

    # ৩. ফেসবুক পেজগুলো থেকে আনা
    for fb_page in FACEBOOK_PAGES:
        all_news.extend(fetch_facebook(fb_page))

    # তারিখ অনুযায়ী নতুনগুলো উপরে সাজানো
    all_news.sort(key=lambda x: x["date"], reverse=True)

    fg = FeedGenerator()
    fg.id("https://github.com/md-muntasir-shihab/rssfeedgenerator")
    fg.title(FEED_TITLE)
    fg.link(href="https://github.com/md-muntasir-shihab/rssfeedgenerator", rel="alternate")
    fg.description(FEED_DESC)
    fg.language("bn")

    unique_items = []
    seen_urls = set()
    for item in all_news:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_items.append(item)

    # ফিডে সর্বোচ্চ ৩৫টি সর্বশেষ পোস্ট থাকবে
    for item in unique_items[:35]:
        entry = fg.add_entry()
        entry.id(item["url"])
        entry.title(item["title"])
        entry.link(href=item["url"])
        entry.pubDate(item["date"])

        if item.get("image"):
            entry.enclosure(url=item["image"], type="image/jpeg", length="0")

        entry.description(item["content"])

    fg.rss_file(FEED_FILE, pretty=True)
    print("Master unified feed generated successfully!")

if __name__ == "__main__":
    build_feed()
