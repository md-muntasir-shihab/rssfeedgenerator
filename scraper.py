import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator

# ==========================================
# আপনার লিংক এখানে বসান:
TARGET_URL = "https://example.com/category-news"  # <-- শুধু এখানে আপনার লিংকটি দিন
FEED_TITLE = "Latest Category Updates"
FEED_DESC = "Automatically updated RSS feed with images and summaries."
# ==========================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "bn-BD,bn;q=0.9,en-US;q=0.8,en;q=0.7",
}

def extract_image(tag, base_url):
    """লেজি-লোড এবং রেটিনা ডিসপ্লে ছবি স্বয়ংক্রিয়ভাবে খুঁজে বের করে"""
    img = tag.find("img")
    if not img:
        return None
    
    # সম্ভাব্য সব ধরনের আধুনিক লেজি-লোড অ্যাট্রিবিউট চেক
    img_src = (
        img.get("data-src")
        or img.get("data-original")
        or img.get("data-lazy-src")
        or img.get("srcset", "").split(",")[0].split(" ")[0]
        or img.get("src")
    )
    if img_src and not img_src.startswith("data:"):
        return urljoin(base_url, img_src)
    return None

def extract_date(tag):
    """নিউজ প্রকাশের সময় বের করার স্মার্ট লজিক"""
    time_tag = tag.find("time")
    if time_tag and time_tag.get("datetime"):
        try:
            return date_parser.parse(time_tag["datetime"])
        except Exception:
            pass
    return datetime.now(timezone.utc)

def scrape_and_build_feed():
    session = requests.Session()
    response = session.get(TARGET_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    fg = FeedGenerator()
    fg.id(TARGET_URL)
    fg.title(FEED_TITLE)
    fg.link(href=TARGET_URL, rel="alternate")
    fg.description(FEED_DESC)
    fg.language("bn")

    # সাইটের নিউজ কার্ডগুলো স্মার্টলি শনাক্ত করা
    cards = soup.find_all("article")
    if not cards or len(cards) < 3:
        cards = soup.select(
            ".news-card, .news-item, .post, .card, .story, .archive-item, .item-details"
        )
    if not cards:
        # কোনো নির্দিষ্ট ক্লাস না মিললে সব বড় হেডিংকে কার্ড হিসেবে ধরা
        cards = [h.find_parent(["div", "li"]) for h in soup.find_all(["h2", "h3"])]
        cards = [c for c in cards if c is not None]

    seen_links = set()
    count = 0

    for card in cards:
        if count >= 20:  # সর্বশেষ ২০টি খবর নেবে
            break

        # টাইটেল ও লিংক বের করা
        heading = card.find(["h1", "h2", "h3", "h4"]) or card.find("a")
        link_tag = card.find("a", href=True)
        if not heading or not link_tag:
            continue

        title = heading.get_text(strip=True)
        link = urljoin(TARGET_URL, link_tag["href"])

        # অপ্রয়োজনীয় লিংক এবং ডুপ্লিকেট বাদ দেওয়া
        if not title or len(title) < 8 or link in seen_links:
            continue
        seen_links.add(link)

        # সামারি / সারসংক্ষেপ
        desc_tag = card.find(["p", ".summary", ".excerpt", ".lead"])
        summary = desc_tag.get_text(strip=True) if desc_tag else title
        summary = re.sub(r"\s+", " ", summary)  # অতিরিক্ত স্পেস ক্লিন করা

        # ছবি ও প্রকাশের সময়
        image_url = extract_image(card, TARGET_URL)
        pub_date = extract_date(card)

        # RSS আইটেম তৈরি
        entry = fg.add_entry()
        entry.id(link)
        entry.title(title)
        entry.link(href=link)
        entry.pubDate(pub_date)

        # রিডারে সুন্দরভাবে প্রদর্শনের জন্য HTML ফরম্যাটিং
        content_parts = []
        if image_url:
            content_parts.append(
                f'<p><img src="{image_url}" alt="{title}" style="max-width:100%; height:auto; border-radius:8px;"/></p>'
            )
            entry.enclosure(url=image_url, type="image/jpeg", length="0")
        
        content_parts.append(f'<p>{summary}</p>')
        entry.description("".join(content_parts))

        count += 1

    fg.rss_file("feed.xml", pretty=True)

if __name__ == "__main__":
    scrape_and_build_feed()
