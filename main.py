import os
import time
import requests
from urllib.parse import urljoin, unquote
from seleniumbase import SB
import re  # For sanitizing filenames

# --- Configuration (!!! MUST ADJUST FOR THE TARGET WEBSITE !!!) ---

# 1. The URL of the *first* page listing the galleries
GALLERY_OVERVIEW_BASE_URL_INPUT = (
    "https://izispicy.com/babes/"  # Or just "/all-galleries" if that's the start
)

# 2. SELECTORS (Use Browser Dev Tools - F12 -> Inspect Element)
#    Replace these placeholders with the actual CSS selectors or XPaths

# -- Selectors for the OVERVIEW Pages --
GALLERY_LINK_SELECTOR = "h1.zag_block>a"  # Selector for links ON THE OVERVIEW page leading to individual galleries
# OVERVIEW_NEXT_PAGE_SELECTOR = "#dle-content > div.paging.c > a:nth-child(3)"  # Selector for the "Next" button/link on the OVERVIEW pages list

# -- Selectors WITHIN an Individual Gallery Page --
GALLERY_TITLE_SELECTOR = "h1.zag_block"  # Optional: Selector for the main title WITHIN a gallery page (for folder name)
IMAGE_SELECTOR = (
    "div.imgbox>a>img"  # Selector for the actual image elements WITHIN a gallery page
)
GALLERY_NEXT_PAGE_SELECTOR = "#post-list > div:nth-child(6) > div > b:nth-child(3) > a"  # Selector for the "Next Page" button/link WITHIN a single gallery's pagination

# 3. Download Settings
DOWNLOAD_FOLDER = "downloaded_galleries"  # Main folder to save all gallery subfolders
START_HEADLESS = False  # Set to True to run without opening a visible browser window (False recommended for debugging)
# PAGE_LOAD_WAIT is NO LONGER NEEDED
REQUEST_TIMEOUT = 30  # Seconds to wait for image download request
ELEMENT_WAIT_TIMEOUT = 20  # Default timeout for sb.wait_for_... methods (seconds)

# --- End Configuration ---


def sanitize_filename(name):
    """Removes or replaces characters invalid for filesystem names."""
    if not isinstance(name, str):
        name = str(name)
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    # Replace sequences of whitespace or multiple underscores with a single underscore
    name = re.sub(r"[\s_]+", "_", name)
    name = name.strip("_ ")
    # Limit length (optional)
    # MAX_LEN = 100
    # if len(name) > MAX_LEN: name = name[:MAX_LEN].rsplit('_', 1)[0] + "_" + name[-5:] # try to keep end part
    return name if name else "untitled_gallery"


def extract_and_format_date(url_string):
    """Finds YYYY/MM/DD in a URL and returns YYYY_MM_DD, or None."""
    match = re.search(r"(\d{4})/(\d{2})/(\d{2})", url_string)
    if match:
        year, month, day = match.groups()
        # Basic validation (optional, but good practice)
        try:
            if (
                1990 <= int(year) <= 2099
                and 1 <= int(month) <= 12
                and 1 <= int(day) <= 31
            ):
                return f"{year}_{month}_{day}"
            else:
                print(
                    f"      Warning: Found date-like pattern ({match.group(0)}) but seems invalid in URL: {url_string}"
                )
                return None
        except ValueError:
            print(
                f"      Warning: Found date-like pattern ({match.group(0)}) but failed numeric conversion in URL: {url_string}"
            )
            return None
    return None


def modify_gallery_title(original_title, date_str):
    """Inserts the date string before '(XX PICS)' in the title."""
    if not date_str or not original_title:
        return original_title  # Return original if no date or title

    # Regex to find the "(XX PICS)" part, allowing for whitespace variations
    # It captures the space before and the entire bracketed part
    pattern = re.compile(r"(\s*\(\s*\d+\s*PICS\s*\)\s*)$", re.IGNORECASE)
    match = pattern.search(original_title)

    if match:
        # Insert the date string and a space before the matched part
        pics_part = match.group(1)
        title_before_pics = original_title[: match.start()]
        return f"{title_before_pics.strip()} {date_str}{pics_part}"
    else:
        # If pattern not found, maybe just append the date? Or return original?
        print(
            f"      Warning: Title '{original_title}' didn't match expected '(XX PICS)' pattern. Appending date."
        )
        return f"{original_title.strip()} {date_str}"


def get_base_overview_url(url_input):
    """Ensures the base URL ends with a slash and removes trailing 'page/N/' if present."""
    # Remove fragment
    url_input = url_input.split("#")[0]
    # Remove query string
    url_input = url_input.split("?")[0]
    # Remove trailing 'page/N/' or 'page/N'
    url_input = re.sub(r"page/\d+/?$", "", url_input)
    # Ensure it ends with a slash
    if not url_input.endswith("/"):
        url_input += "/"
    return url_input


def download_image(img_url, save_path, session):
    """Downloads a single image using the provided requests session."""
    try:
        print(f"          Attempting download: {img_url}")
        response = session.get(img_url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"          SUCCESS: Saved to {save_path}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"          ERROR downloading {img_url}: {e}")
    except IOError as e:
        print(f"          ERROR saving file {save_path}: {e}")
    except Exception as e:
        print(f"          UNEXPECTED ERROR for {img_url}: {e}")
    return False


# --- Main Script Logic ---
if __name__ == "__main__":
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    processed_gallery_urls = set()  # Keep track of galleries already processed

    # Prepare base URL for overview pagination
    base_overview_url = get_base_overview_url(GALLERY_OVERVIEW_BASE_URL_INPUT)
    print(f"Using Base Overview URL for pagination: {base_overview_url}")

    # Use a requests session for efficient downloading
    download_session = requests.Session()
    download_session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    )

    try:
        with SB(uc=True, headless=START_HEADLESS) as sb:
            overview_page_num = 1

            # --- Outer Loop: Iterate through Overview Pages using URL construction ---
            while True:  # Loop will break internally when no more content is found
                current_overview_page_url = (
                    f"{base_overview_url}page/{overview_page_num}/"
                )
                print(
                    f"\n{'='*10} Attempting Overview Page {overview_page_num}: {current_overview_page_url} {'='*10}"
                )

                try:
                    sb.open(current_overview_page_url)
                    # Check if page loaded correctly (e.g., not a 404 redirected to homepage)
                    # A simple check is to see if the URL is still what we expect
                    # More robust check: wait for a known element *specific* to overview pages
                    if sb.get_current_url().rstrip(
                        "/"
                    ) != current_overview_page_url.rstrip("/"):
                        print(
                            f"  Redirected from expected URL. Current URL: {sb.get_current_url()}"
                        )
                        print("  Assuming end of overview pages due to redirect.")
                        break  # Stop if URL changed unexpectedly (like redirect on 404)

                    print(
                        f"  Waiting for gallery links using selector: '{GALLERY_LINK_SELECTOR}'"
                    )
                    # Wait for *at least one* element to be present (or timeout)
                    # We use is_element_present check *after* this wait.
                    try:
                        sb.wait_for_element_present(
                            GALLERY_LINK_SELECTOR, timeout=ELEMENT_WAIT_TIMEOUT
                        )
                    except Exception:
                        print(
                            f"  No gallery links appeared within timeout ({ELEMENT_WAIT_TIMEOUT}s)."
                        )
                        # Proceed to the is_element_present check which should also fail

                    # --- Check if any gallery links exist on the page ---
                    if not sb.is_element_present(GALLERY_LINK_SELECTOR):
                        print(
                            f"  No gallery links found using selector '{GALLERY_LINK_SELECTOR}' on overview page {overview_page_num}."
                        )
                        print(f"  Assuming this is the end of the overview pages.")
                        break  # Break the outer WHILE loop

                    # --- Collect Gallery Links ONLY from THIS Overview Page ---
                    gallery_links_on_this_page = []
                    gallery_elements = sb.find_elements(
                        GALLERY_LINK_SELECTOR
                    )  # Find all links
                    print(
                        f"  Found {len(gallery_elements)} potential gallery links on this overview page."
                    )

                    for element in gallery_elements:
                        href = element.get_attribute("href")
                        if href and href.strip():
                            # Base URL for resolving relative links is the current overview page
                            full_url = urljoin(sb.get_current_url(), href.strip())
                            if full_url not in processed_gallery_urls:
                                if full_url not in [
                                    g["url"] for g in gallery_links_on_this_page
                                ]:
                                    gallery_links_on_this_page.append({"url": full_url})
                            # else: print(f"    Skipping already processed gallery: {full_url}") # Optional logging

                    print(
                        f"  Found {len(gallery_links_on_this_page)} new unique gallery links to process from this page."
                    )

                    # --- Process Each Gallery Found on THIS Overview Page ---
                    for i, gallery_info in enumerate(gallery_links_on_this_page):
                        gallery_url = gallery_info["url"]
                        print(
                            f"\n    ---> Processing Gallery {i + 1}/{len(gallery_links_on_this_page)} from Overview Page {overview_page_num}: {gallery_url}"
                        )

                        # --- Inner Gallery Processing Logic ---
                        current_page_in_gallery = 1
                        total_images_in_gallery = 0
                        gallery_name = "untitled_gallery"  # Default
                        gallery_folder = None
                        formatted_date = extract_and_format_date(
                            gallery_url
                        )  # Extract date from gallery URL

                        try:
                            sb.open(gallery_url)  # Navigate to the specific gallery
                            print(f"      Opened gallery page. Waiting for title...")
                            sb.wait_for_element_visible(
                                GALLERY_TITLE_SELECTOR, timeout=ELEMENT_WAIT_TIMEOUT
                            )
                            original_title = sb.get_text(GALLERY_TITLE_SELECTOR)

                            # Modify title with date
                            modified_title = modify_gallery_title(
                                original_title, formatted_date
                            )
                            gallery_name = sanitize_filename(
                                modified_title
                            )  # Sanitize the final name

                            gallery_folder = os.path.join(DOWNLOAD_FOLDER, gallery_name)
                            os.makedirs(gallery_folder, exist_ok=True)
                            print(
                                f"      Gallery Name: '{gallery_name}' (Date: {formatted_date or 'Not Found'})"
                            )
                            print(f"      Saving images to: '{gallery_folder}'")

                            # --- Innermost Loop: Handle pagination WITHIN this gallery ---
                            while True:
                                print(
                                    f"\n        Scraping Page {current_page_in_gallery} in gallery '{gallery_name}'..."
                                )
                                print(f"        Current URL: {sb.get_current_url()}")
                                page_images_downloaded = 0

                                try:
                                    print(
                                        f"        Waiting for images using selector: '{IMAGE_SELECTOR}'"
                                    )
                                    sb.wait_for_element_present(
                                        IMAGE_SELECTOR, timeout=ELEMENT_WAIT_TIMEOUT
                                    )
                                except Exception:
                                    print(
                                        f"        Warning: No images found or appeared on page {current_page_in_gallery} within timeout."
                                    )
                                    # Still check for next page button below

                                if not sb.is_element_present(IMAGE_SELECTOR):
                                    print(
                                        f"        No images present on page {current_page_in_gallery} using selector '{IMAGE_SELECTOR}'."
                                    )
                                    # Check if it's the end or just an empty page
                                    if (
                                        not sb.is_element_present(
                                            GALLERY_NEXT_PAGE_SELECTOR
                                        )
                                        and current_page_in_gallery > 1
                                    ):
                                        print(
                                            "        Also no 'Next' button found. Assuming end of gallery."
                                        )
                                        break
                                    elif current_page_in_gallery == 1:
                                        print(
                                            "        This was the first page. Checking for 'Next' button anyway."
                                        )
                                    else:
                                        print("        Checking for 'Next' button...")
                                    # Fall through to check the next page button

                                image_elements = sb.find_elements(
                                    IMAGE_SELECTOR
                                )  # Find images if present
                                print(
                                    f"        Found {len(image_elements)} image elements on this page."
                                )

                                for img_element in image_elements:
                                    # --- Image Downloading ---
                                    img_src = img_element.get_attribute("src")
                                    if not img_src or not img_src.strip():
                                        print(
                                            "          Warning: Found image tag with empty src."
                                        )
                                        continue
                                    img_src = img_src.strip()
                                    absolute_img_url = urljoin(
                                        sb.get_current_url(), img_src
                                    )  # Base is current gallery page

                                    try:  # Generate filename
                                        filename_part = unquote(
                                            absolute_img_url.split("/")[-1].split("?")[
                                                0
                                            ]
                                        )
                                        if "." not in filename_part[-6:]:
                                            filename = f"{sanitize_filename(filename_part)}.jpg"  # Append default ext if missing
                                        else:
                                            filename = sanitize_filename(filename_part)
                                        if not filename or filename.startswith("."):
                                            raise ValueError(
                                                "Generated invalid filename"
                                            )
                                    except Exception as e:
                                        print(
                                            f"          Warning: Could not derive filename from URL ({e}). Using sequential name."
                                        )
                                        file_ext = os.path.splitext(absolute_img_url)[1]
                                        if not file_ext or len(file_ext) > 5:
                                            file_ext = ".jpg"
                                        filename = f"image_{total_images_in_gallery + page_images_downloaded + 1:04d}{file_ext}"

                                    save_path = os.path.join(gallery_folder, filename)
                                    if download_image(
                                        absolute_img_url, save_path, download_session
                                    ):
                                        page_images_downloaded += 1
                                        # time.sleep(0.05) # Tiny optional delay between downloads for politeness
                                    # --- End Image Downloading ---

                                total_images_in_gallery += page_images_downloaded
                                print(
                                    f"        Downloaded {page_images_downloaded} images from page {current_page_in_gallery}."
                                )

                                # --- Check for GALLERY Next Page ---
                                print(
                                    f"        Checking for Gallery 'Next Page' using selector: '{GALLERY_NEXT_PAGE_SELECTOR}'"
                                )
                                if sb.is_element_visible(
                                    GALLERY_NEXT_PAGE_SELECTOR
                                ):  # Check visibility is better
                                    try:
                                        print(
                                            "        Gallery 'Next Page' button found. Clicking..."
                                        )
                                        sb.click(GALLERY_NEXT_PAGE_SELECTOR)
                                        current_page_in_gallery += 1
                                        print(
                                            f"        Clicked next. Waiting for elements on gallery page {current_page_in_gallery}..."
                                        )
                                        # No fixed sleep! Rely on wait_for_element_present at start of loop.
                                    except Exception as click_err:
                                        print(
                                            f"        Error clicking Gallery 'Next Page' button: {click_err}. Assuming end of gallery."
                                        )
                                        break
                                else:
                                    print(
                                        "        No Gallery 'Next Page' button visible. Assuming end of gallery."
                                    )
                                    break
                                # --- End GALLERY Next Page Check ---
                            # --- End Innermost Loop (Gallery Pagination) ---

                        except Exception as gallery_err:
                            print(
                                f"      ERROR processing gallery '{gallery_name or gallery_url}': {gallery_err}"
                            )
                            # Log error but continue processing other galleries from this overview page

                        finally:
                            # Mark gallery as processed AFTER attempting it
                            processed_gallery_urls.add(gallery_url)
                            print(
                                f"    ---> Finished attempt for gallery '{gallery_name}'. Total images downloaded: {total_images_in_gallery}"
                            )
                        # --- End Inner Gallery Processing ---
                    # --- End Loop for Galleries on This Overview Page ---

                    # --- Prepare for Next Overview Page ---
                    overview_page_num += (
                        1  # Increment page number for the next iteration
                    )

                except Exception as overview_page_err:
                    print(
                        f"  MAJOR ERROR processing overview page {current_overview_page_url}: {overview_page_err}"
                    )
                    print("  Stopping script due to error on overview page.")
                    break  # Stop the outer loop
            # --- End Outer Loop (Overview Pages) ---

    except Exception as e:
        print(f"\nAn unexpected error occurred during the browser session: {e}")
    finally:
        download_session.close()  # Close the requests session
        print(
            f"\n--- Script Finished. Processed {len(processed_gallery_urls)} unique galleries across {overview_page_num -1} attempted overview pages. ---"
        )
