import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
import openai
from dotenv import load_dotenv
import uvicorn
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
serper_api_key = os.getenv("SERP_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

class KeywordData(BaseModel):
    keyword: str

def scrape_site(url: str):
    try:
        response = requests.get(url)
        if response.status_code != 200:
            logger.warning(f"Failed to scrape {url}, status code: {response.status_code}")
            return None
        soup = BeautifulSoup(response.content, 'html.parser')
        scraped_data = {tag: [elem.get_text(strip=True) for elem in soup.find_all(tag)] for tag in ['h1', 'h2', 'h3']}
        logger.info(f"Scraped data from {url}")
        return scraped_data
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return None

@app.post("/generate_content_brief/")
async def generate_content_brief(data: KeywordData):
    logger.info(f"Received request for keyword: {data.keyword}")

    # Fetch top sites from SERP
    serp_url = "https://google.serper.dev/search"
    request_data = {
        "q": data.keyword,
        "page": 10,
        "gl": "us"
    }
    headers = {
        'X-API-KEY': serper_api_key,
        'Content-Type': 'application/json',
    }
    try:
        serp_response = requests.post(serp_url, headers=headers, json=request_data)
        if serp_response.status_code != 200:
            error_detail = f"Error fetching data from SERP API for keyword '{data.keyword}'"
            logger.error(error_detail)
            raise HTTPException(status_code=400, detail=error_detail)
        top_sites = [item['link'] for item in serp_response.json().get('organic', [])][:10]
        logger.info(f"Top sites fetched for {data.keyword}")
    except Exception as e:
        logger.error(f"Error fetching top sites: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    # Scrape sites for tags
    consolidated_data = {}
    for site in top_sites:
        site_data = scrape_site(site)
        if site_data:
            for tag, contents in site_data.items():
                if tag not in consolidated_data:
                    consolidated_data[tag] = []
                consolidated_data[tag].extend(contents)
    logger.info(f"Data scraped for all sites for {data.keyword}")

    # Prepare message for OpenAI
    detailed_message = f"Consider the most relevant information, avoid fluff, and provide a concise yet comprehensive brief about the intent & content using the top ranking sites, focusing particularly on the keyword: '{data.keyword}': \n\n"
    for tag, texts in consolidated_data.items():
        detailed_message += f"{tag.upper()}: {' '.join(texts[:5])}\n\n"

    # Call OpenAI API for content brief
    try:
        openai.api_key = openai_api_key
        completion = openai.ChatCompletion.create(
            model="gpt-4-1106-preview",
            messages=[
                {"role": "system", "content": "You are a seasoned SEO expert and content strategist. Your task is to analyze the following consolidated data from top-ranking websites and provide a hyper-optimized content brief & optimal structure outline with the data of the heading given. This brief should be actionable and clear for content writers, highlighting key points and takeaways.\n\n Use the keyword's intent & context. Generate an optimized content brief with content idea thesis, specifying whether it's a content piece, a calculator, a landing page, or other. Format the brief in Markdown."},
                {"role": "user", "content": detailed_message}
            ]
        )
        logger.info(f"Content brief generated for {data.keyword}")
        return {"content_brief": completion.choices[0].message["content"]}
    except Exception as e:
        logger.error(f"Error generating content brief: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=10000)
