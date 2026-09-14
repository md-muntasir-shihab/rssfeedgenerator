import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator
import trafilatura

URL_LIST = [
    "https://www.bbc.com/bengali"
]

FEED_TITLE = "BBC News Bangla - Auto Feed"
FEED_DESC = "Clean, full-text news feed updated automatically."
FEED_FILE = "feed.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def clean_text_content(raw_text):
    """মার্কডাউন ট্যাগ, অপ্রয়োজনীয় লিংক ও ফুটনোট মুছে লেখা ঝকঝকে করে"""
    if not raw_text:
        return ""
    # মার্কডাউন ছবি বাদ দেওয়া: ![alt](url)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', raw_text)
    # মার্কডাউন লিংক টেক্সট রাখা: [text](url) -> text
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    # মার্কডাউন বোল্ড/ইটালিক বাদ দেওয়া
    text = text.replace('**', '').replace('*', '')
    # বিবিসির সাইডবার/হোয়াটসঅ্যাপ ফুটনোট ফিল্টার
    text = re.sub(r'আপনার হোয়াটসঅ্যাপে.*', '', text, flags=re.DOTALL)
    text = re.sub(r'বিবিসি বাংলার অন্যান্য খবর.*', '', text, flags=re.DOTALL)
    return text.strip()

def parse_full_article(article_url):
    try:
        res = requests.get(article_url, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            return None

        page_soup = BeautifulSoup(res.text, "html.parser")
        downloaded = res.text

        metadata = trafilatura.extract_metadata(downloaded)
        full_text = trafilatura.extract(downloaded, output_format="txt")

        title = metadata.title if metadata and metadata.title else None
        if not title and page_soup.title:
            title = page_soup.title.get_text().split("-")[0].strip()

        if not title:
            return None

        # আসল কাভার ছবি খোঁজা
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

        cleaned_text = clean_text_content(full_text)
        paragraphs = [f"<p>{p.strip()}</p>" for p in cleaned_text.split("\n\n") if len(p.strip()) > 25]

        # সুন্দর HTML কনটেন্ট তৈরি
        content_parts = []
        if image_url:
            content_parts.append(f'<p><img src="{image_url}" alt="{title}" style="max-width:100%; border-radius:8px;"/></p>')
        
        content_parts.extend(paragraphs[:6])
        content_html = "".join(content_parts) if content_parts else f"<p>{title}</p>"

        return {
            "title": title.strip(),
            "url": article_url,
            "image": image_url,
            "date": pub_date,
            "content": content_html
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

        for link in discovered_links[:8]:
            data = parse_full_article(link)
            if data:
                items.append(data)
    except Exception as e:
        print(f"Error: {e}")
    return items

def build_feed():
    all_news = []
    for url in URL_LIST:
        all_news.extend(process_target_url(url))

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

    for item in unique_items[:20]:
        entry = fg.add_entry()
        entry.id(item["url"])
        entry.title(item["title"])
        entry.link(href=item["url"])
        entry.pubDate(item["date"])

        if item.get("image"):
            entry.enclosure(url=item["image"], type="image/jpeg", length="0")

        entry.description(item["content"])

    fg.rss_file(FEED_FILE, pretty=True)
    print("Clean feed generated successfully!")

if __name__ == "__main__":
    build_feed()
