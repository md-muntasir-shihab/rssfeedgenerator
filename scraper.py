import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator
import trafilatura

# ==============================================================
# ১. আপনার কাঙ্ক্ষিত ক্যাটাগরির লিংক এখানে বসান:
TARGET_URL = "https://example.com/technology" 
FEED_TITLE = "Auto Full-Text Category Feed"
FEED_DESC = "Extracted full news, images and content every 30 minutes."
# ==============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def get_article_links(category_url):
    """ক্যাটাগরি পেজ থেকে সংবাদের ইন্ডিভিজুয়াল লিংকগুলো সংগ্রহ করে"""
    response = requests.get(category_url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    discovered_links = []
    seen = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        full_url = urljoin(category_url, href)

        # হোমপেজ, ক্যাটাগরি বা অপ্রয়োজনীয় লিংক বাদ দেওয়ার ফিল্টার
        if (
            full_url == category_url
            or full_url in seen
            or any(x in full_url for x in ["#", "/tag/", "/category/", "/author/", "facebook.com", "twitter.com"])
        ):
            continue

        # লিংকটি আসল কোনো নিউজের পেজ কিনা তা যাচাই
        if len(full_url.replace(category_url, "")) > 5:
            seen.add(full_url)
            discovered_links.append(full_url)

    return discovered_links[:10]  # প্রতি রান-এ সর্বশেষ ১০টি আর্টিকেলের ভেতরে ঢুকবে


def extract_full_article(article_url):
    """আর্টিকেলের লিংকের ভেতর ঢুকে সম্পূর্ণ লেখা, ছবি ও তারিখ বের করে"""
    downloaded = trafilatura.fetch_url(article_url)
    if not downloaded:
        return None

    # মেটাডাটা ও মূল কনটেন্ট পার্সিং
    metadata = trafilatura.extract_metadata(downloaded)
    full_text = trafilatura.extract(
        downloaded,
        include_images=True,
        include_formatting=True,
        output_format="txt"
    )

    if not metadata or not full_text:
        return None

    title = metadata.title
    image_url = metadata.image
    date_val = metadata.date

    # তারিখ কনভার্ট করা
    try:
        pub_date = date_parser.parse(date_val).replace(tzinfo=timezone.utc) if date_val else datetime.now(timezone.utc)
    except Exception:
        pub_date = datetime.now(timezone.utc)

    # সাধারণ টেক্সটকে সুন্দর HTML প্যারাগ্রাফে রূপান্তর
    paragraphs = [f"<p>{p.strip()}</p>" for p in full_text.split("\n\n") if p.strip()]
    article_html = "".join(paragraphs)

    return {
        "title": title,
        "url": article_url,
        "image": image_url,
        "date": pub_date,
        "content_html": article_html
    }


def generate_rss():
    links = get_article_links(TARGET_URL)
    
    fg = FeedGenerator()
    fg.id(TARGET_URL)
    fg.title(FEED_TITLE)
    fg.link(href=TARGET_URL, rel="alternate")
    fg.description(FEED_DESC)
    fg.language("bn")

    for link in links:
        try:
            data = extract_full_article(link)
            if not data or not data["title"]:
                continue

            entry = fg.add_entry()
            entry.id(data["url"])
            entry.title(data["title"])
            entry.link(href=data["url"])
            entry.pubDate(data["date"])

            # আর্টিকেলের শুরুতে বড় ছবি যুক্ত করা
            content = ""
            if data["image"]:
                content += f'<p><img src="{data["image"]}" alt="{data["title"]}" style="max-width:100%; height:auto; border-radius:8px;"/></p>'
                entry.enclosure(url=data["image"], type="image/jpeg", length="0")

            # সম্পূর্ণ আর্টিকেল বডি যুক্ত করা
            content += data["content_html"]
            entry.description(content)

        except Exception as err:
            print(f"Error scraping {link}: {err}")
            continue

    fg.rss_file("feed.xml", pretty=True)


if __name__ == "__main__":
    generate_rss()
