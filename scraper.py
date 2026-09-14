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
#                      এখানে আপনার পছন্দের সব লিংক দিন
# ==============================================================================
# যেকোনো নিউজ সাইট, ব্লগ বা ক্যাটাগরির লিংক এখানে দিন (যত ইচ্ছা যোগ করতে পারবেন)
URL_LIST = [
    "https://www.bbc.com/bengali/topics/c2dwqnw1m9yt",
    "https://prothomalo.com/technology",
    # "https://example.com/another-site",
]

# টেলিগ্রামের পাবলিক চ্যানেল (থাকলে নাম দিন, না থাকলে খালি রাখুন: [])
TELEGRAM_CHANNELS = [
    "du_news_portal"
]

FEED_TITLE = "My Universal Automated Feed"
FEED_DESC = "Clean, full-text news and high-resolution images from any source."
FEED_FILE = "feed.xml"
# ==============================================================================

# আসল ব্রাউজার নকল করার হেডার (যাতে ব্লক না খায়)
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "bn-BD,bn;q=0.9,en-US;q=0.8,en;q=0.7",
})

def find_native_rss(soup, base_url):
    """সাইটের ভেতরে অফিশিয়াল RSS ফিড লুকানো আছে কিনা খোঁজে"""
    link = soup.find("link", type=re.compile(r"application/(rss|atom)\+xml"))
    if link and link.get("href"):
        return urljoin(base_url, link["href"])
    return None

def extract_image_smart(soup, base_url):
    """হাই-রেজুলেশন ছবি ও ওপেনগ্রাফ মেটা ইমেজ বের করে"""
    # ১. ওপেনগ্রাফ ও টুইটার মেটা ট্যাগ (সবচেয়ে ক্লিয়ার ছবি থাকে)
    for prop in ["og:image", "twitter:image", "image"]:
        meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if meta and meta.get("content"):
            return urljoin(base_url, meta["content"])

    # ২. পেজের ভেতরের বড় ছবি
    for img in soup.find_all("img"):
        src = (
            img.get("data-src")
            or img.get("data-original")
            or img.get("data-lazy-src")
            or img.get("src")
        )
        if src and not src.startswith("data:") and not any(x in src.lower() for x in ["icon", "logo", "avatar"]):
            return urljoin(base_url, src)
    return None

def parse_full_article(article_url):
    """সংবাদের ভেতরে ঢুকে বিজ্ঞাপন বাদ দিয়ে ফুল আর্টিকেল নিয়ে আসে"""
    try:
        res = SESSION.get(article_url, timeout=12)
        if res.status_code != 200:
            return None

        page_soup = BeautifulSoup(res.text, "html.parser")
        downloaded = res.text

        # Trafilatura দিয়ে মূল লেখা ফিল্টার
        metadata = trafilatura.extract_metadata(downloaded)
        full_text = trafilatura.extract(
            downloaded,
            include_images=True,
            include_formatting=True,
            output_format="txt"
        )

        title = metadata.title if metadata and metadata.title else None
        if not title and page_soup.title:
            title = page_soup.title.get_text().split("-")[0].split("|")[0].strip()

        if not title:
            return None

        # ছবি নির্ধারণ
        image_url = metadata.image if (metadata and metadata.image) else extract_image_smart(page_soup, article_url)

        # তারিখ নির্ধারণ
        pub_date = datetime.now(timezone.utc)
        if metadata and metadata.date:
            try:
                pub_date = date_parser.parse(metadata.date).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        # প্যারাগ্রাফ সাজানো
        if full_text and len(full_text) > 80:
            paragraphs = "".join([f"<p>{p.strip()}</p>" for p in full_text.split("\n\n") if p.strip()])
        else:
            # ব্যাকআপ প্যারাগ্রাফ
            p_tags = [p.get_text().strip() for p in page_soup.find_all("p") if len(p.get_text().strip()) > 40]
            paragraphs = "".join([f"<p>{p}</p>" for p in p_tags[:8]])

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
    """যেকোনো সাইট সুন্দরভাবে হ্যান্ডেল করার মাস্টার প্রসেসর"""
    items = []
    try:
        res = SESSION.get(target_url, timeout=15)
        if res.status_code != 200:
            return items

        soup = BeautifulSoup(res.text, "html.parser")

        # ১. যদি সাইটের নিজস্ব লাইভ আরএসএস থাকে, সেখান থেকে আনা
        native_rss = find_native_rss(soup, target_url)
        if native_rss:
            feed = feedparser.parse(native_rss)
            for entry in feed.entries[:6]:
                link = entry.get("link", "")
                pub_d = datetime.now(timezone.utc)
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_d = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                # ভেতরে ঢুকে সম্পূর্ণ আর্টিকেল ও বড় ছবি নেওয়া
                detailed = parse_full_article(link)
                if detailed:
                    items.append(detailed)
                else:
                    items.append({
                        "title": entry.get("title", ""),
                        "url": link,
                        "image": None,
                        "date": pub_d,
                        "content": entry.get("summary", "")
                    })
            if items:
                return items

        # ২. নিজস্ব আরএসএস না থাকলে পেজ স্ক্র্যাপ করা
        discovered_links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            full_url = urljoin(target_url, a["href"].strip())
            if full_url == target_url or full_url in seen:
                continue
            if any(bad in full_url.lower() for bad in ["#", "/tag/", "/category/", "facebook", "twitter", "login"]):
                continue
            if len(full_url.replace(target_url, "")) > 4:
                seen.add(full_url)
                discovered_links.append(full_url)

        # শীর্ষ ৫টি নতুন সংবাদের বিস্তারিত নিয়ে আসা
        for link in discovered_links[:5]:
            article_data = parse_full_article(link)
            if article_data:
                items.append(article_data)

    except Exception as e:
        print(f"Skipping {target_url} due to error: {e}")
    return items

def scrape_telegram(channel):
    """টেলিগ্রামের পাবলিক মেসেজ সংগ্রহ"""
    items = []
    try:
        url = f"https://t.me/s/{channel}"
        res = SESSION.get(url, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        for msg in soup.find_all("div", class_="tgme_widget_message_wrap")[-5:]:
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
                "title": f"[Telegram] {title}",
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

    # সব ওয়েবসাইট প্রসেস করা
    for url in URL_LIST:
        all_news.extend(process_target_url(url))

    # টেলিগ্রাম প্রসেস করা
    for ch in TELEGRAM_CHANNELS:
        all_news.extend(scrape_telegram(ch))

    if not all_news:
        print("No news could be gathered.")
        return

    # তারিখ অনুযায়ী একদম নতুন পোস্টগুলো উপরে সাজানো
    all_news.sort(key=lambda x: x["date"], reverse=True)

    # ডুপ্লিকেট বাদ দেওয়া
    unique_items = []
    seen_urls = set()
    for item in all_news:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_items.append(item)

    fg = FeedGenerator()
    fg.id("https://github.com/md-muntasir-shihab/rssfeedgenerator")
    fg.title(FEED_TITLE)
    fg.link(href="https://github.com/md-muntasir-shihab/rssfeedgenerator", rel="alternate")
    fg.description(FEED_DESC)
    fg.language("bn")

    # শীর্ষ ২৫টি নিউজ নিয়ে ফিড তৈরি
    for item in unique_items[:25]:
        entry = fg.add_entry()
        entry.id(item["url"])
        entry.title(item["title"])
        entry.link(href=item["url"])
        entry.pubDate(item["date"])

        body = ""
        if item["image"]:
            body += f'<p><img src="{item["image"]}" alt="{item["title"]}" style="max-width:100%; height:auto; border-radius:8px;"/></p>'
            entry.enclosure(url=item["image"], type="image/jpeg", length="0")

        body += item["content"]
        entry.description(body)

    fg.rss_file(FEED_FILE, pretty=True)
    print("Master clean feed generated successfully!")

if __name__ == "__main__":
    build_feed()
