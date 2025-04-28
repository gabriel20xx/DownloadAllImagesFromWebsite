import os
import requests
from urllib.parse import urljoin, unquote, urlparse
from bs4 import BeautifulSoup
import yaml
import re

# --- Configuration (Using values from user log/previous context) ---
GALLERY_OVERVIEW_BASE_URL_INPUT = "https://izispicy.com/babes/"
GALLERY_LINK_SELECTOR = "h1.zag_block > a"
GALLERY_TITLE_SELECTOR = "h1.zag_block"
IMAGE_SELECTOR = "div.imgbox img"
GALLERY_NEXT_PAGE_SELECTOR = (
    "#post-list > div:nth-child(6) > div > b:nth-child(3) > a"  # From user log
)

DOWNLOAD_FOLDER = "Z:/Samples/Izispicy"
REQUEST_TIMEOUT = 30
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_SKIP_PHRASE = "(VIDEO)"  # <<< Phrase to check for skipping
# --- End Configuration ---


# Helper functions (sanitize_filename, extract_and_format_date, etc.) remain the same...
def sanitize_filename(name):
    """Sanitizes a string for use as a filename."""
    if not isinstance(name, str):
        name = str(name)
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"[\s_]+", "_", name)
    name = name.strip("_ ")
    # Avoid making filename just the date if title was only VIDEO skip phrase
    if name == extract_and_format_date(
        name
    ):  # Check if name *only* contains the formatted date
        return f"{name}_gallery"
    return name if name else "untitled_gallery"


def extract_and_format_date(url_string):
    """Extracts and formats a date from a URL string."""
    match = re.search(r"(\d{4})/(\d{2})/(\d{2})", url_string)
    if match:
        year, month, day = match.groups()
        try:
            if (
                1990 <= int(year) <= 2099
                and 1 <= int(month) <= 12
                and 1 <= int(day) <= 31
            ):
                return f"{year}_{month}_{day}"
        except ValueError:
            pass
    return None


def extract_count_from_title(title_string):
    """Extracts image count from a title string like '(XX PICS)'."""
    if not title_string:
        return None
    match = re.search(r"\(\s*(\d+)\s*PICS?\s*\)", title_string, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def modify_gallery_title(original_title, date_str):
    """Modifies the gallery title, adding date if present and removing video phrase."""
    # Remove the video phrase before adding date/pics part if present
    title_no_video = original_title.replace(VIDEO_SKIP_PHRASE, "").strip()
    if not title_no_video:  # Handle case where title was *only* the video phrase
        return date_str if date_str else "video_gallery"

    if not date_str:
        return title_no_video  # Return title without video phrase if no date

    pattern = re.compile(r"(\s*\(\s*\d+\s*PICS?\s*\)\s*)$", re.IGNORECASE)
    match = pattern.search(title_no_video)
    if match:
        pics_part = match.group(1)
        title_before_pics = title_no_video[: match.start()]
        return f"{title_before_pics.strip()} {date_str}{pics_part}"
    else:  # Append date if no "(XX PICS)" found after removing video phrase
        return f"{title_no_video.strip()} {date_str}"


def get_base_overview_url(url_input):
    """Determines the base URL for overview pagination."""
    url_input = url_input.split("#")[0].split("?")[0]
    url_input = re.sub(r"page/\d+/?$", "", url_input)
    if not url_input.endswith("/"):
        url_input += "/"
    return url_input


def count_image_files(dir_path):
    """Counts image files in a directory based on defined extensions."""
    if not os.path.isdir(dir_path):
        return 0
    count = 0
    try:
        for fname in os.listdir(dir_path):
            if os.path.isfile(os.path.join(dir_path, fname)):
                if os.path.splitext(fname)[1].lower() in IMAGE_EXTENSIONS:
                    count += 1
    except OSError as e:
        print(f"      Warning: Could not count files in {dir_path}: {e}")
        return 0
    return count


def download_image(img_url, save_path, session):
    """Downloads an image using a requests session."""
    try:
        # print(f"        Attempting download: {img_url}") # Too verbose?
        response = session.get(img_url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        # print(f"        SUCCESS: Saved locally to {save_path}") # Too verbose?
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"          HTTP ERROR downloading {img_url}: {http_err}")
    except requests.exceptions.RequestException as e:
        print(f"          ERROR downloading {img_url}: {e}")
    except IOError as e:
        print(f"          ERROR saving file {save_path}: {e}")
    except Exception as e:
        print(f"          UNEXPECTED ERROR for {img_url}: {e}")
    return False


def get_soup(url, session, timeout=REQUEST_TIMEOUT):
    """Fetches a URL using requests and returns a BeautifulSoup object."""
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        return BeautifulSoup(response.content, "lxml"), response.url
    except requests.exceptions.RequestException as e:
        print(f"      ERROR fetching {url}: {e}")
        return None, None
    except Exception as e:
        print(f"      ERROR parsing {url}: {e}")
        return None, None


# --- Main Script Logic ---
if __name__ == "__main__":
    config_name = "config.yaml"
    config = {}  # Initialize config as an empty dictionary

    try:
        with open(config_name, "r") as config_file:
            loaded_config = yaml.safe_load(config_file)
            if loaded_config:  # Ensure loaded_config is not None
                config = loaded_config
    except FileNotFoundError:
        print(f"Configuration file '{config_name}' not found. Using default values.")
    except yaml.YAMLError as e:
        print(
            f"Error loading configuration file '{config_name}': {e}. Using default values."
        )
    except Exception as e:
        print(
            f"An unexpected error occurred while loading config: {e}. Using default values."
        )

    # --- Apply Configuration (Loading from file, falling back to defaults) ---
    GALLERY_OVERVIEW_BASE_URL_INPUT = config.get(
        "GALLERY_OVERVIEW_BASE_URL_INPUT", GALLERY_OVERVIEW_BASE_URL_INPUT
    )
    DOWNLOAD_FOLDER = config.get("DOWNLOAD_FOLDER", DOWNLOAD_FOLDER)
    # Ensure IMAGE_EXTENSIONS remains a set after loading from yaml (list in yaml -> set in code)
    loaded_extensions = config.get(
        "IMAGE_EXTENSIONS", list(IMAGE_EXTENSIONS)
    )  # Get as list if from yaml
    IMAGE_EXTENSIONS = (
        set(loaded_extensions)
        if isinstance(loaded_extensions, (list, tuple, set))
        else set()
    )  # Convert to set, handle unexpected types
    VIDEO_SKIP_PHRASE = config.get("VIDEO_SKIP_PHRASE", VIDEO_SKIP_PHRASE)
    GALLERY_LINK_SELECTOR = config.get("GALLERY_LINK_SELECTOR", GALLERY_LINK_SELECTOR)
    GALLERY_TITLE_SELECTOR = config.get(
        "GALLERY_TITLE_SELECTOR", GALLERY_TITLE_SELECTOR
    )
    IMAGE_SELECTOR = config.get("IMAGE_SELECTOR", IMAGE_SELECTOR)
    GALLERY_NEXT_PAGE_SELECTOR = config.get(
        "GALLERY_NEXT_PAGE_SELECTOR", GALLERY_NEXT_PAGE_SELECTOR
    )
    REQUEST_TIMEOUT = config.get("REQUEST_TIMEOUT", REQUEST_TIMEOUT)
    # --- End Applying Configuration ---

    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    processed_or_skipped_urls = (
        set()
    )  # To track galleries we've decided *not* to process again

    base_overview_url = get_base_overview_url(GALLERY_OVERVIEW_BASE_URL_INPUT)
    print(f"Using Base Overview URL for pagination: {base_overview_url}")

    # Use one session for overview pages for potential cookie handling
    overview_session = requests.Session()
    overview_session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    )

    overview_page_num = 1

    # --- Outer Loop: Iterate through Overview Pages ---
    while True:
        current_overview_page_url = f"{base_overview_url}page/{overview_page_num}/"
        print(
            f"\n{'='*10} Attempting Overview Page {overview_page_num}: {current_overview_page_url} {'='*10}"
        )

        soup_overview, actual_overview_url = get_soup(
            current_overview_page_url, overview_session
        )

        if soup_overview is None:
            print(
                f"  Failed to fetch or parse overview page {overview_page_num}. Assuming end."
            )
            break

        # Check for redirects that might indicate end of pages
        expected_path = urlparse(current_overview_page_url).path.rstrip("/")
        actual_path = urlparse(actual_overview_url).path.rstrip("/")
        if actual_path != expected_path:
            # This check is more complex browserless. A simple 301/302 might
            # automatically redirect to page 1 or the last page.
            # Let's rely more on finding gallery links.
            print(
                f"  Redirected from expected URL path ({expected_path} -> {actual_path}). Continuing..."
            )
            # If redirected *away* from the expected pagination pattern,
            # it might be the end, but let's still check for links.
            # A better check might be if the actual URL is the base URL without /page/X/

        # --- Collect Gallery Links ---
        gallery_links_on_this_page = []
        gallery_elements = soup_overview.select(GALLERY_LINK_SELECTOR)
        print(
            f"  Found {len(gallery_elements)} potential gallery link elements on this overview page."
        )

        if not gallery_elements:
            print(
                f"  No gallery links found on overview page {overview_page_num}. Assuming end."
            )
            break  # No links means end of overview pages

        for element in gallery_elements:
            href = element.get("href")
            if href and href.strip():
                full_url = urljoin(actual_overview_url, href.strip())
                if full_url not in processed_or_skipped_urls:
                    # Avoid adding duplicates from the same overview page scrape
                    if full_url not in [g["url"] for g in gallery_links_on_this_page]:
                        gallery_links_on_this_page.append({"url": full_url})
        print(
            f"  Found {len(gallery_links_on_this_page)} new unique gallery links to check/process from this page."
        )

        # --- Process Each Gallery Found on THIS Overview Page ---
        for i, gallery_info in enumerate(gallery_links_on_this_page):
            gallery_url = gallery_info["url"]
            gallery_name = "untitled_gallery"
            gallery_folder_path = None

            print(
                f"\n    ---> Checking Gallery {i + 1}/{len(gallery_links_on_this_page)}: {gallery_url}"
            )

            # Use a new session for each gallery to simulate isolation/cookie clearing
            gallery_session = requests.Session()
            gallery_session.headers.update(overview_session.headers)  # Use same headers

            try:
                # Step 1: Fetch gallery page, get title, determine potential folder name
                print(f"      Fetching gallery page: {gallery_url}")
                soup_gallery, actual_gallery_url = get_soup(
                    gallery_url, gallery_session
                )

                if soup_gallery is None:
                    print("      Failed to fetch or parse gallery page. Skipping.")
                    processed_or_skipped_urls.add(
                        gallery_url
                    )  # Mark as checked/skipped
                    continue

                title_element = soup_gallery.select_one(GALLERY_TITLE_SELECTOR)
                original_title = (
                    title_element.get_text().strip() if title_element else "Untitled"
                )
                print(f"      Original Title: '{original_title}'")

                # <<< Add Check for VIDEO_SKIP_PHRASE >>>
                if VIDEO_SKIP_PHRASE in original_title:
                    print(f"      SKIPPING: Title contains '{VIDEO_SKIP_PHRASE}'.")
                    processed_or_skipped_urls.add(gallery_url)  # Mark as skipped
                    continue  # Skip to the next gallery URL
                # <<< End VIDEO Check >>>

                # Proceed with naming and other checks only if not a video
                expected_count = extract_count_from_title(original_title)
                formatted_date = extract_and_format_date(gallery_url)
                modified_title = modify_gallery_title(original_title, formatted_date)
                gallery_name = sanitize_filename(modified_title)
                gallery_folder_path = os.path.join(DOWNLOAD_FOLDER, gallery_name)

                print(f"      Gallery Name (used for folder): '{gallery_name}'")
                print(
                    f"      Expected Image Count from Title: {expected_count if expected_count is not None else 'Unknown'}"
                )
                print(f"      Checking Folder Path: '{gallery_folder_path}'")

                # Step 2: Check folder existence and compare counts
                folder_exists = os.path.exists(gallery_folder_path)
                local_file_count = 0
                if folder_exists:
                    local_file_count = count_image_files(gallery_folder_path)
                    print(
                        f"      Folder exists. Local image file count: {local_file_count}"
                    )

                # Decision Point: Skip only if folder exists AND counts match (or exceed)
                if (
                    folder_exists
                    and expected_count is not None
                    and expected_count > 0
                    and local_file_count >= expected_count
                ):
                    print(
                        f"      SKIPPING download/pagination: Local count ({local_file_count}) >= Expected count ({expected_count})."
                    )
                    processed_or_skipped_urls.add(gallery_url)  # Mark as skipped
                    continue  # Skip to the next gallery URL
                elif folder_exists:
                    print(
                        f"      PROCESSING: Folder exists but local count ({local_file_count}) < expected count ({expected_count or 'Unknown'}), or expected count unknown. Will check for missing images."
                    )
                else:  # Folder doesn't exist
                    print(
                        f"      PROCESSING: Folder not found. Proceeding with full download."
                    )

                processed_or_skipped_urls.add(
                    gallery_url
                )  # Mark as checked/processing now

                # --- Step 3: Process Images & Pagination (Only if not skipped) ---
                total_images_downloaded_this_run = 0
                current_page_in_gallery = 1
                current_gallery_page_url = actual_gallery_url  # Start with the first page URL we already fetched

                # Innermost Loop: Handle pagination WITHIN this gallery
                while True:
                    print(
                        f"\n        Scraping Page {current_page_in_gallery} in gallery '{gallery_name}'..."
                    )
                    print(f"        Current URL: {current_gallery_page_url}")

                    # If this isn't the first page, we need to fetch it now
                    if current_page_in_gallery > 1:
                        soup_gallery, actual_gallery_url = get_soup(
                            current_gallery_page_url, gallery_session
                        )
                        if soup_gallery is None:
                            print(
                                f"        Failed to fetch or parse gallery page {current_page_in_gallery}. Assuming end of gallery."
                            )
                            break  # Cannot fetch next page, end gallery processing

                    image_elements = soup_gallery.select(IMAGE_SELECTOR)
                    print(
                        f"        Found {len(image_elements)} image elements on this page."
                    )
                    page_images_downloaded_this_run = 0

                    if not image_elements:
                        print(
                            f"        No images present on page {current_page_in_gallery} ('{IMAGE_SELECTOR}')."
                        )
                        # Continue to check for next page button, as in original logic

                    # --- Image Downloading ---
                    for img_element in image_elements:
                        img_src = img_element.get("src")
                        if not img_src or not img_src.strip():
                            continue
                        img_src = img_src.strip()
                        # Use the actual URL of the current page for urljoin
                        absolute_img_url = urljoin(actual_gallery_url, img_src)

                        try:  # Generate filename
                            filename_part = unquote(
                                absolute_img_url.split("/")[-1].split("?")[0]
                            )
                            file_ext_lower = os.path.splitext(filename_part)[1].lower()
                            if file_ext_lower not in IMAGE_EXTENSIONS:
                                filename = f"{sanitize_filename(filename_part)}.jpg"  # Assume .jpg if no valid extension
                            else:
                                filename = sanitize_filename(filename_part)
                            if not filename or filename.startswith("."):
                                # Fallback if sanitization results in empty or dot file
                                raise ValueError("Generated invalid filename")
                        except Exception as e:
                            # Fallback filename if URL parsing/sanitization fails
                            file_ext = os.path.splitext(absolute_img_url)[1].lower()
                            if file_ext not in IMAGE_EXTENSIONS:
                                file_ext = ".jpg"
                            img_counter = (
                                local_file_count
                                + total_images_downloaded_this_run
                                + page_images_downloaded_this_run
                                + 1
                            )
                            filename = f"image_{img_counter:04d}{file_ext}"
                            print(
                                f"          Warning: Could not derive filename from URL ({e}). Using: {filename} for {absolute_img_url}"
                            )

                        save_path = os.path.join(gallery_folder_path, filename)

                        # Optimization: Skip download if file already exists
                        if os.path.exists(save_path):
                            # print(f"          File already exists: {save_path}. Skipping.") # Too verbose?
                            continue

                        # Ensure directory exists BEFORE download attempt
                        current_folder_exists_check = os.path.exists(
                            gallery_folder_path
                        )
                        if not current_folder_exists_check:
                            try:
                                print(
                                    f"        Creating folder: '{gallery_folder_path}'"
                                )
                                os.makedirs(gallery_folder_path, exist_ok=True)
                                current_folder_exists_check = True  # Update status
                            except OSError as oe:
                                print(
                                    f"        ERROR creating directory {gallery_folder_path}: {oe}. Skipping image {absolute_img_url}."
                                )
                                continue  # Skip this image

                        # Attempt Download only if folder exists
                        if current_folder_exists_check:
                            # Pass the gallery-specific session to download_image
                            if download_image(
                                absolute_img_url,
                                save_path,
                                gallery_session,
                            ):
                                page_images_downloaded_this_run += 1
                                total_images_downloaded_this_run += 1
                        # --- End Image Downloading ---
                    # End image element loop

                    print(
                        f"        Downloaded {page_images_downloaded_this_run} new images from page {current_page_in_gallery}."
                    )

                    # --- Check for GALLERY Next Page ---
                    print(
                        f"        Checking for Gallery 'Next Page' ('{GALLERY_NEXT_PAGE_SELECTOR}')"
                    )
                    next_page_element = soup_gallery.select_one(
                        GALLERY_NEXT_PAGE_SELECTOR
                    )

                    if next_page_element:
                        next_page_href = next_page_element.get("href")
                        if next_page_href and next_page_href.strip():
                            current_gallery_page_url = urljoin(
                                actual_gallery_url, next_page_href.strip()
                            )
                            current_page_in_gallery += 1
                            print(
                                f"        Gallery 'Next Page' button found. Will attempt to fetch: {current_gallery_page_url}"
                            )
                            # The loop will fetch the new URL in the next iteration
                        else:
                            print(
                                "        Gallery 'Next Page' button found, but href is empty. Assuming end of gallery."
                            )
                            break  # No valid href, end gallery processing
                    else:
                        print(
                            "        No 'Next Page' button found. Assuming end of gallery."
                        )
                        break  # No next page element, end gallery processing
                    # --- End GALLERY Next Page Check ---
                # --- End Innermost Loop (Gallery Pagination) ---

                # --- Final logging for this gallery ---
                # This block is only reached if the gallery was NOT skipped by VIDEO or Count checks
                final_local_count = count_image_files(gallery_folder_path)
                print(f"\n    ---> Finished PROCESSING gallery '{gallery_name}'.")
                print(
                    f"      Downloaded {total_images_downloaded_this_run} new images in this run for this gallery."
                )
                if os.path.isdir(gallery_folder_path):
                    print(
                        f"      Folder '{gallery_folder_path}' now contains {final_local_count} images."
                    )
                    if (
                        expected_count is not None
                        and final_local_count < expected_count
                    ):
                        print(
                            f"      WARNING: Final count ({final_local_count}) is less than expected ({expected_count})."
                        )
                elif total_images_downloaded_this_run > 0:
                    print(
                        f"      WARNING: Images were downloaded but folder '{gallery_folder_path}' cannot be confirmed."
                    )
                else:
                    print(f"      No new images downloaded for this gallery.")

            except Exception as gallery_err:
                # Catch errors during fetching, parsing, or the main processing block for a single gallery
                print(
                    f"      ERROR processing gallery '{gallery_name or gallery_url}': {gallery_err}"
                )
                # The URL is already added to processed_or_skipped_urls at the start of processing

            finally:
                # The gallery_session will go out of scope and be garbage collected
                # when the inner `for` loop finishes, effectively clearing cookies.
                pass  # No explicit cleanup needed for the session object

            # Add a small delay between galleries to be polite
            # time.sleep(1) # Optional: import time

        # --- End Loop for Galleries on This Overview Page ---

        # --- Prepare for Next Overview Page ---
        overview_page_num += 1

    # --- End Outer Loop (Overview Pages) ---

    overview_session.close()  # Close the session used for overview pages

    print(
        f"\n--- Script Finished. Attempted {overview_page_num -1} overview pages. Checked/Processed/Skipped {len(processed_or_skipped_urls)} unique gallery URLs. ---"
    )
