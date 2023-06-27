import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urlencode, urlunparse, parse_qs
import time
from PyQt5.QtWidgets import QApplication, QFileDialog

# Create the application
app = QApplication([])


def generate_urls(base_url, max_page):
    urls = []
    parsed_url = urlparse(base_url)
    query_params = parse_qs(parsed_url.query)

    start_page = int(query_params.get('page', [1])[0])

    for page in range(start_page, max_page + 1):
        query_params['page'] = [str(page)]
        encoded_query = urlencode(query_params, doseq=True)
        parsed_url = parsed_url._replace(query=encoded_query)
        updated_url = urlunparse(parsed_url)
        urls.append(updated_url)

    return urls


def download_image(url, directory):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        filename = os.path.basename(urlparse(url).path)
        filepath = os.path.join(directory, filename)

        if os.path.exists(filepath):
            print(f"Skipping image (already exists): {url}")
            return

        with open(filepath, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)

        print(f"Downloaded: {url}")
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {url}: {e}")
    except IOError as e:
        print(f"IOError while saving {url}: {e}")


def download_images_from_website(website_url, target_directory, minimum_image_size, delay):
    # Create target directory if it doesn't exist
    os.makedirs(target_directory, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/91.0.4472.124 Safari/537.36",
        "Referer": website_url
    }

    try:
        response = requests.get(website_url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error accessing website: {e}")
        return

    soup = BeautifulSoup(response.content, "html.parser")

    for img_tag in soup.find_all("img"):
        img_url = img_tag.get("src")

        if img_url:
            absolute_img_url = urljoin(website_url, img_url)
            print(f"\nPage {i} from {max_page}")
            print(f"Checking image: {absolute_img_url}")
            try:
                image_response = requests.head(absolute_img_url)
                image_size = int(image_response.headers.get("content-length", 0))

                if image_size > minimum_image_size * 1024:  # Convert to bytes
                    print(f"Downloading image: {absolute_img_url}")
                    download_image(absolute_img_url, target_directory)
                    time.sleep(delay)  # Delay of 1 second between each request
                else:
                    print(f"Skipping image (less than {minimum_image_size} KB): {absolute_img_url}")
            except requests.exceptions.RequestException as e:
                print(f"Error accessing image: {e}")


# Define output directory
while True:
    print("Choose your output folder")
    target_directory = QFileDialog.getExistingDirectory(None, "Select output folder")

    if target_directory:
        break


while True:
    link = input("Type in link: ")

    if link:
        break


while True:
    max_page = int(input("Enter the maximum page number: "))

    if max_page:
        break

while True:
    minimum_image_size = int(input("Type minimum picture size in kb: "))

    if minimum_image_size:
        break


while True:
    delay = int(input("Type delay in seconds: "))

    if delay:
        break


generated_urls = generate_urls(link, max_page)

for i, url in enumerate(generated_urls, 1):
    domain = urlparse(url).netloc
    target_directory_with_domain = os.path.join(target_directory, domain)
    print(f"Downloading images from page {i} to directory: {target_directory_with_domain}")
    download_images_from_website(url, target_directory_with_domain, minimum_image_size, delay)
