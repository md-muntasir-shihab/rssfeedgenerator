import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator
import trafilatura

# ==============================================================================
#                  ১. আপনার লাইভ নিউজ লিংক ও চ্যানেল
# ==============================================================================
URL_LIST = [
    "https://www.bbc.com/bengali"  # বিবিসি বাংলার মূল লাইভ পেজ
]

TELEGRAM_CHANNELS = [
    "bbc_news_bangla"  # বিবিসি বাংলার অফিশিয়াল টেলিগ্রাম
]

FEED_TITLE = "My Automated News Feed"
FEED_DESC = "Clean, full-text news feed updated automatically every 30 minutes."
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

def parse_full_article(article_url):
    try:
        res = requests.get(article_url, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            return None

        page_soup = BeautifulSoup(res.text, "html.parser")
        downloaded = res.text

        metadata = trafilatura.extract_metadata(downloaded)
        full_text = trafilatura.extract(
            downloaded,
            include_images=True,
            include_formatting=True,
            output_format="txt"
        )

        title = metadata.title if metadata and metadata.title else None
        if not title and page_soup.title:
            title = page_soup.title.get_text().split("-")[0].strip()

        if not title:
            return None

        image_url = metadata.image if (metadata and metadata.image) else None
        if not image_url:
            og_img = page_soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                image_url = urljoin(article_url, og_img["content"])

        pub_date = datetime.now(timezone.utc)
        if metadata and metadata.date:
            try:
                pub_date = date_parser.parse(metadata.date).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        if full_text and len(full_text) > 80:
            paragraphs = "".join([f"<p>{p.strip()}</p>" for p in full_text.split("\n\n") if p.strip()])
        else:
            paragraphs = f"<p>{title}</p>"

        return {
            "title": title.strip(),
            "url": article_url,
            "image": image_url,
            "date": pub_date,
            "content": paragraphs
        }
    except Exception:
        return None

def process_target_url(target_url):
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
            if any(bad in full_url.lower() for bad in ["#", "/tag/", "/category/", "facebook", "twitter", "login"]):
                continue
            if "/articles/" in full_url or "/news-" in full_url:
                seen.add(full_url)
                discovered_links.append(full_url)

        for link in discovered_links[:6]:
            article_data = parse_full_article(link)
            if article_data:
                items.append(article_data)

    except Exception as e:
        print(f"Error scraping {target_url}: {e}")
    return items

def scrape_telegram(channel):
    items = []
    try:
        url = f"https://t.me/s/{channel}"
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return items

        soup = BeautifulSoup(res.text, "html.parser")
        for msg in soup.find_all("div", class_="tgme_widget_message_wrap")[-6:]:
            text_el = msg.find("div", class_="tgme_widget_message_text")
            date_el = msg.find("time")
            link_el = msg.find("a", class_="tgme_widget_message_date")
            if not text_el or not link_el:
                continue

            raw_text = text_el.get_text(separator="\n", strip=True)
            title = raw_text[:80] + "..." if len(raw_text) > 80 else raw_text
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
                "title": f"[BBC] {title}",
                "url": post_link,
                "image": image_url,
                "date": pub_date,
                "content": html_body
            })
    except Exception as e:
        print(f"Telegram error: {e}")
    return items

def build_feed():
    all_news = []
    for url in URL_LIST:
        all_news.extend(process_target_url(url))

    for ch in TELEGRAM_CHANNELS:
        all_news.extend(scrape_telegram(ch))

    all_news.sort(key=lambda x: x["date"], reverse=True)

    fg = FeedGenerator()
    fg.id("https://github.com/md-muntasir-shihab/rssfeedgenerator")
    fg.title(FEED_TITLE)
    fg.link(href="https://github.com/md-muntasir-shihab/rssfeedgenerator", rel="alternate")
    fg.description(FEED_DESC)
    fg.language("bn")

    if not all_news:
        entry = fg.add_entry()
        entry.id("https://github.com/md-muntasir-shihab/rssfeedgenerator#init")
        entry.title("Feed Active - Scanning for New Articles")
        entry.link(href="https://github.com/md-muntasir-shihab/rssfeedgenerator")
        entry.pubDate(datetime.now(timezone.utc))
        entry.description("<p>Feed generator is active and waiting for new stories.</p>")
    else:
        unique_items = []
        seen_urls = set()
        for item in all_news:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                unique_items.append(item)

        for item in unique_items[:25]:
            entry = fg.add_entry()
            entry.id(item["url"])
            entry.title(item["title"])
            entry.link(href=item["url"])
            entry.pubDate(item["date"])

            body = ""
            if item.get("image"):
                body += f'<p><img src="{item["image"]}" alt="{item["title"]}" style="max-width:100%; height:auto; border-radius:8px;"/></p>'
                entry.enclosure(url=item["image"], type="image/jpeg", length="0")

            body += item["content"]
            entry.description(body)

    fg.rss_file(FEED_FILE, pretty=True)
    print("Master clean feed generated successfully!")

if __name__ == "__main__":
    build_feed()
