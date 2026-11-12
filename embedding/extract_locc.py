
import json
import re
import string
import requests
import pdfplumber
import io
import time

BASE_URL = "https://loc.gov/aba/cataloging/classification/lcco/lcco_{}.pdf"

# LCC main classes (I, O, W, X, Y are not assigned)
LETTERS = [letter for letter in string.ascii_uppercase if letter not in ["I", "O", "W", "X", "Y"]]

def extract_class(letter):
    if letter == "E":
        return {
            "title": "History of the Americas",
            "subclasses": {}
        }

    if letter == "F":
        return {
            "title": "Local History of the Americas",
            "subclasses": {}
        }

    url = BASE_URL.format(letter.lower())

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # read only the first PDF page
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            if not pdf.pages:
                return None

            text = pdf.pages[0].extract_text() or ""

        # extract main class title
        title_match = re.search(rf"CLASS\s+{letter}\s*[-]\s*(.+)", text, re.IGNORECASE)

        title = title_match.group(1).strip() if title_match else None

        # extract subclass codes and descriptions
        subclasses = {}

        lines = text.splitlines()

        for line in lines:
            line = line.strip()

            # match one- or two-letter subclass codes
            match = re.match(r"Subclass\s+([A-Z]{1,2})\s+(.+)$", line)

            if match:
                code = match.group(1)
                description = match.group(2).strip()

                # avoid capturing unrelated headings
                if code.startswith(letter):
                    subclasses[code] = description

        return {
            "title": title,
            "subclasses": subclasses
        }

    except requests.RequestException as e:
        print(f"[HTTP ERROR] {letter}: {e}")
    except Exception as e:
        print(f"[ERROR] {letter}: {e}")

    return None


def main():
    results = {}

    for letter in LETTERS:
        print(f"processing class {letter}...")

        data = extract_class(letter)

        if data:
            results[letter] = data
            print(f"  found {len(data['subclasses'])} subclasses")

        # be polite to the LOC server
        time.sleep(1.5)

    with open("lcc_outline.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nextraction done - {len(results)} classes.")
    print("saved to lcc_outline.json")

if __name__ == "__main__":
    main()