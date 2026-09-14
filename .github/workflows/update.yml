name: Update RSS Every 30 Minutes

on:
  schedule:
    - cron: '*/30 * * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scrape-and-update:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Dependencies
        run: |
          pip install -r requirements.txt

      - name: Run Full Scraper
        run: |
          python scraper.py

      - name: Push Feed Changes
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          if [ -f feed.xml ]; then
            git add feed.xml
            git diff --quiet && git diff --staged --quiet || (git commit -m "Auto update feed.xml [skip ci]" && git push)
          else
            echo "feed.xml was not created"
            exit 1
          fi
