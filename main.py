import os
import requests
from urllib.parse import urljoin, unquote
from seleniumbase import SB
import re  # For sanitizing filenames

# --- Configuration (!!! MUST ADJUST FOR THE TARGET WEBSITE !!!) ---
GALLERY_OVERVIEW_BASE_URL_INPUT = "https://izispicy.com/babes/"
GALLERY_LINK_SELECTOR = "h1.zag_block>a"  # Selector for links ON THE OVERVIEW page leading to individual galleries
GALLERY_TITLE_SELECTOR = "h1.zag_block"  # Optional: Selector for the main title WITHIN a gallery page (for folder name)
IMAGE_SELECTOR = "div.imgbox>a>img"
GALLERY_NEXT_PAGE_SELECTOR = "#post-list > div:nth-child(6) > div > b:nth-child(3) > a"  # Selector for the "Next Page" button/link WITHIN a single gallery's pagination
DOWNLOAD_FOLDER = "downloaded_galleries"  # Main folder to save all gallery subfolders
START_HEADLESS = False
REQUEST_TIMEOUT = 30  # Seconds to wait for image download request
ELEMENT_WAIT_TIMEOUT = 20  # Default timeout for sb.wait_for_... methods (seconds)
# Define common image extensions for counting and checking existing files
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
# --- End Configuration ---


def sanitize_filename(name):
    """Removes or replaces characters invalid for filesystem names."""
    if not isinstance(name, str):
        name = str(name)
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"[\s_]+", "_", name)
    name = name.strip("_ ")
    return name if name else "untitled_gallery"


def extract_and_format_date(url_string):
    """Finds sediment/MM/DD in a URL and returns sediment_MM_DD, or None."""
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
    """Extracts the number from '(XX PICS)' in the title. Returns int or None."""
    if not title_string:
        return None
    match = re.search(r"\((\d+)\s*PICS\)", title_string, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def modify_gallery_title(original_title, date_str):
    """Inserts the date string before '(XX PICS)' in the title."""
    if not date_str or not original_title:
        return original_title
    pattern = re.compile(r"(\s*\(\s*\d+\s*PICS\s*\)\s*)$", re.IGNORECASE)
    match = pattern.search(original_title)
    if match:
        pics_part = match.group(1)
        title_before_pics = original_title[: match.start()]
        return f"{title_before_pics.strip()} {date_str}{pics_part}"
    else:
        return f"{original_title.strip()} {date_str}"


def get_base_overview_url(url_input):
    """Prepares the base URL for overview pagination."""
    url_input = url_input.split("#")[0].split("?")[0]
    url_input = re.sub(r"page/\d+/?$", "", url_input)
    if not url_input.endswith("/"):
        url_input += "/"
    return url_input


def count_image_files(dir_path):
    """Counts files with common image extensions in a directory."""
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
    """Downloads a single image. Returns True on success."""
    # Directory check/creation is now handled *before* calling this function.
    try:
        print(f"          Attempting download: {img_url}")
        response = session.get(img_url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"          SUCCESS: Saved locally to {save_path}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"          ERROR downloading {img_url}: {e}")
    # Catch specific file errors if needed, like permissions, but Errno 2 should be gone.
    except IOError as e:
        print(f"          ERROR saving file {save_path}: {e}")
    except Exception as e:
        print(f"          UNEXPECTED ERROR for {img_url}: {e}")
    return False


# --- Main Script Logic ---
if __name__ == "__main__":
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    processed_or_skipped_urls = set()

    base_overview_url = get_base_overview_url(GALLERY_OVERVIEW_BASE_URL_INPUT)
    print(f"Using Base Overview URL for pagination: {base_overview_url}")

    download_session = requests.Session()
    download_session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    )

    try:
        with SB(uc=True, headless=START_HEADLESS) as sb:
            overview_page_num = 1

            # --- Outer Loop: Iterate through Overview Pages ---
            while True:
                current_overview_page_url = (
                    f"{base_overview_url}page/{overview_page_num}/"
                )
                print(
                    f"\n{'='*10} Attempting Overview Page {overview_page_num}: {current_overview_page_url} {'='*10}"
                )

                try:
                    sb.open(current_overview_page_url)
                    expected_url_base = current_overview_page_url.rstrip("/")
                    actual_url_base = sb.get_current_url().rstrip("/")
                    if (
                        actual_url_base != expected_url_base
                        and not actual_url_base.startswith(expected_url_base)
                    ):
                        print(
                            f"  Redirected from expected URL. Assuming end of overview pages."
                        )
                        break

                    print(f"  Waiting for gallery links ('{GALLERY_LINK_SELECTOR}')")
                    try:
                        sb.wait_for_element_present(
                            GALLERY_LINK_SELECTOR, timeout=ELEMENT_WAIT_TIMEOUT
                        )
                    except Exception:
                        pass

                    if not sb.is_element_present(GALLERY_LINK_SELECTOR):
                        print(
                            f"  No gallery links found on overview page {overview_page_num}. Assuming end."
                        )
                        break

                    # --- Collect Gallery Links from THIS Overview Page ---
                    gallery_links_on_this_page = []
                    gallery_elements = sb.find_elements(GALLERY_LINK_SELECTOR)
                    print(
                        f"  Found {len(gallery_elements)} potential gallery links on this overview page."
                    )
                    for element in gallery_elements:
                        href = element.get_attribute("href")
                        if href and href.strip():
                            full_url = urljoin(sb.get_current_url(), href.strip())
                            if full_url not in processed_or_skipped_urls:
                                if full_url not in [
                                    g["url"] for g in gallery_links_on_this_page
                                ]:
                                    gallery_links_on_this_page.append({"url": full_url})
                    print(
                        f"  Found {len(gallery_links_on_this_page)} new unique gallery links to check/process."
                    )

                    # --- Process Each Gallery Found on THIS Overview Page ---
                    for i, gallery_info in enumerate(gallery_links_on_this_page):
                        gallery_url = gallery_info["url"]
                        gallery_name = "untitled_gallery"
                        gallery_folder_path = None
                        processed_or_skipped_urls.add(gallery_url)

                        print(
                            f"\n    ---> Checking Gallery {i + 1}/{len(gallery_links_on_this_page)}: {gallery_url}"
                        )

                        try:
                            # Step 1: Open gallery, get title, expected count, determine folder path
                            sb.open(gallery_url)
                            print(
                                f"      Opened gallery page. Waiting for title ('{GALLERY_TITLE_SELECTOR}')..."
                            )
                            sb.wait_for_element_visible(
                                GALLERY_TITLE_SELECTOR, timeout=ELEMENT_WAIT_TIMEOUT
                            )
                            # Use the full text of the title element, assuming it contains "(XX PICS)"
                            original_title = sb.get_text(GALLERY_TITLE_SELECTOR).strip()

                            expected_count = extract_count_from_title(original_title)
                            formatted_date = extract_and_format_date(gallery_url)
                            modified_title = modify_gallery_title(
                                original_title, formatted_date
                            )
                            gallery_name = sanitize_filename(modified_title)
                            gallery_folder_path = os.path.join(
                                DOWNLOAD_FOLDER, gallery_name
                            )

                            print(f"      Gallery Name: '{gallery_name}'")
                            print(
                                f"      Expected Image Count from Title: {expected_count if expected_count is not None else 'Unknown'}"
                            )
                            print(
                                f"      Checking Folder Path: '{gallery_folder_path}'"
                            )

                            # Step 2: Check folder existence and compare counts
                            folder_exists = os.path.exists(gallery_folder_path)
                            local_file_count = 0
                            if folder_exists:
                                local_file_count = count_image_files(
                                    gallery_folder_path
                                )
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
                                    f"    SKIPPING download/pagination: Local count ({local_file_count}) >= Expected count ({expected_count})."
                                )
                                continue  # Skip to the next gallery URL
                            elif folder_exists:
                                print(
                                    f"    PROCESSING: Folder exists but local count ({local_file_count}) < expected count ({expected_count or 'Unknown'}), or expected count unknown. Will check for missing images."
                                )
                            else:  # Folder doesn't exist
                                print(
                                    f"    PROCESSING: Folder not found. Proceeding with full download."
                                )
                            # --- End Skip Logic ---

                            # --- Step 3: Process Images & Pagination (Only if not skipped) ---
                            # Flag to track if *this run* created the folder. Initialize based on initial check.
                            folder_created_this_run = (
                                False  # <<< Changed flag name slightly for clarity
                            )
                            total_images_downloaded_this_run = 0
                            current_page_in_gallery = 1

                            # Innermost Loop: Handle pagination WITHIN this gallery
                            while True:
                                print(
                                    f"\n        Scraping Page {current_page_in_gallery} in gallery '{gallery_name}'..."
                                )
                                print(f"        Current URL: {sb.get_current_url()}")

                                try:
                                    print(
                                        f"        Waiting for images ('{IMAGE_SELECTOR}')"
                                    )
                                    sb.wait_for_element_present(
                                        IMAGE_SELECTOR, timeout=ELEMENT_WAIT_TIMEOUT
                                    )
                                except Exception:
                                    pass

                                if not sb.is_element_present(IMAGE_SELECTOR):
                                    print(
                                        f"        No images present on page {current_page_in_gallery} ('{IMAGE_SELECTOR}')."
                                    )
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
                                    # else continue below to check next page button

                                image_elements = sb.find_elements(IMAGE_SELECTOR)
                                print(
                                    f"        Found {len(image_elements)} image elements on this page."
                                )
                                page_images_downloaded_this_run = 0

                                for img_element in image_elements:
                                    # --- Image Downloading ---
                                    img_src = img_element.get_attribute("src")
                                    if not img_src or not img_src.strip():
                                        continue
                                    img_src = img_src.strip()
                                    absolute_img_url = urljoin(
                                        sb.get_current_url(), img_src
                                    )

                                    try:  # Generate filename
                                        filename_part = unquote(
                                            absolute_img_url.split("/")[-1].split("?")[
                                                0
                                            ]
                                        )
                                        file_ext_lower = os.path.splitext(
                                            filename_part
                                        )[1].lower()
                                        if file_ext_lower not in IMAGE_EXTENSIONS:
                                            filename = f"{sanitize_filename(filename_part)}.jpg"
                                        else:
                                            filename = sanitize_filename(filename_part)
                                        if not filename or filename.startswith("."):
                                            raise ValueError(
                                                "Generated invalid filename"
                                            )
                                    except Exception as e:
                                        file_ext = os.path.splitext(absolute_img_url)[
                                            1
                                        ].lower()
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
                                            f"          Warning: Could not derive filename from URL ({e}). Using: {filename}"
                                        )

                                    save_path = os.path.join(
                                        gallery_folder_path, filename
                                    )

                                    # --- Optimization: Skip download if file already exists ---
                                    # Check this *before* trying to create the folder or download
                                    if os.path.exists(save_path):
                                        # print(f"          Skipping download: File already exists at {save_path}") # Optional: Verbose logging
                                        continue  # Skip to next image element
                                    # --- End Optimization ---

                                    # --- Ensure directory exists BEFORE download attempt ---
                                    # Try to create only if it didn't exist initially OR if creation wasn't flagged as done this run
                                    if (
                                        not folder_exists
                                        and not folder_created_this_run
                                    ):
                                        try:
                                            print(
                                                f"        Creating folder for first image: '{gallery_folder_path}'"
                                            )
                                            os.makedirs(
                                                gallery_folder_path, exist_ok=True
                                            )
                                            # Update flags immediately after successful creation
                                            folder_exists = (
                                                True  # Mark that it now exists
                                            )
                                            folder_created_this_run = True
                                            print(
                                                f"        (Saving subsequent images to this folder)"
                                            )
                                        except OSError as oe:
                                            print(
                                                f"        ERROR creating directory {gallery_folder_path}: {oe}. Skipping image download."
                                            )
                                            # Cannot download if dir creation failed, skip to next image
                                            continue  # Skip this image if folder creation failed
                                    elif not folder_exists and folder_created_this_run:
                                        # This case shouldn't happen if logic is right, but indicates folder exists now
                                        pass  # Folder was created earlier in this gallery's processing

                                    # --- Attempt Download only if folder exists ---
                                    if (
                                        folder_exists
                                    ):  # Check if folder exists (either initially or created just now)
                                        if download_image(
                                            absolute_img_url,
                                            save_path,
                                            download_session,
                                        ):
                                            page_images_downloaded_this_run += 1
                                            total_images_downloaded_this_run += 1
                                    else:
                                        print(
                                            f"          Skipping download for {filename} because directory does not exist and creation failed."
                                        )
                                    # --- End Image Downloading ---
                                # End image loop

                                print(
                                    f"        Downloaded {page_images_downloaded_this_run} new images from page {current_page_in_gallery}."
                                )

                                # --- Check for GALLERY Next Page ---
                                print(
                                    f"        Checking for Gallery 'Next Page' ('{GALLERY_NEXT_PAGE_SELECTOR}')"
                                )
                                # Try the more general selector first
                                next_button_found = False
                                if sb.is_element_visible(GALLERY_NEXT_PAGE_SELECTOR):
                                    try:
                                        # Verify it's actually clickable/intended link (optional refinement)
                                        print(
                                            "        Gallery 'Next Page' button found (using primary selector). Clicking..."
                                        )
                                        sb.click(GALLERY_NEXT_PAGE_SELECTOR)
                                        next_button_found = True
                                    except Exception as click_err:
                                        print(
                                            f"        Error clicking primary 'Next Page' button: {click_err}."
                                        )
                                        # Consider trying the fallback selector if primary fails?

                                # Example of trying a fallback selector (adjust if needed)
                                # if not next_button_found:
                                #      fallback_selector = "#post-list > div:nth-child(6) > div > b:nth-child(3) > a"
                                #      print(f"        Checking for Gallery 'Next Page' (using fallback selector: '{fallback_selector}')")
                                #      if sb.is_element_visible(fallback_selector):
                                #           try:
                                #                print("        Gallery 'Next Page' button found (using fallback selector). Clicking...")
                                #                sb.click(fallback_selector)
                                #                next_button_found = True
                                #           except Exception as click_err_fallback:
                                #                print(f"        Error clicking fallback 'Next Page' button: {click_err_fallback}.")

                                if next_button_found:
                                    current_page_in_gallery += 1
                                    print(
                                        f"        Clicked next. Waiting for elements on gallery page {current_page_in_gallery}..."
                                    )
                                else:
                                    print(
                                        "        No visible 'Next Page' button found using configured selectors. Assuming end of gallery."
                                    )
                                    break  # Exit pagination loop
                                # --- End GALLERY Next Page Check ---
                            # --- End Innermost Loop (Gallery Pagination) ---

                            # --- Final logging for this gallery ---
                            final_local_count = count_image_files(
                                gallery_folder_path
                            )  # Recount at the end
                            print(
                                f"    ---> Finished PROCESSING gallery '{gallery_name}'."
                            )
                            print(
                                f"         Downloaded {total_images_downloaded_this_run} new images in this run."
                            )
                            if os.path.isdir(
                                gallery_folder_path
                            ):  # Check if folder exists before counting
                                print(
                                    f"         Folder '{gallery_folder_path}' now contains {final_local_count} images."
                                )
                                if (
                                    expected_count is not None
                                    and final_local_count < expected_count
                                ):
                                    print(
                                        f"         WARNING: Final count ({final_local_count}) is less than expected ({expected_count})."
                                    )
                            else:
                                print(
                                    f"         Folder '{gallery_folder_path}' was NOT created (no images downloaded)."
                                )

                        except Exception as gallery_err:
                            print(
                                f"      ERROR processing gallery '{gallery_name or gallery_url}': {gallery_err}"
                            )
                            # URL already added to processed_or_skipped_urls set
                        # --- End Inner Gallery Processing Block ---
                    # --- End Loop for Galleries on This Overview Page ---

                    # --- Prepare for Next Overview Page ---
                    overview_page_num += 1

                except Exception as overview_page_err:
                    print(
                        f"  MAJOR ERROR processing overview page {current_overview_page_url}: {overview_page_err}"
                    )
                    print("  Stopping script due to error on overview page.")
                    break
            # --- End Outer Loop (Overview Pages) ---

    except Exception as e:
        print(f"\nAn unexpected error occurred during the browser session: {e}")
    finally:
        download_session.close()
        print(
            f"\n--- Script Finished. Attempted {overview_page_num -1} overview pages. Checked/Processed/Skipped {len(processed_or_skipped_urls)} unique gallery URLs. ---"
        )
